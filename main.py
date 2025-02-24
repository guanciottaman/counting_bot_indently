"""Counting Discord bot for Indently server"""
import asyncio
import json
import os
import sqlite3
import string
from dataclasses import dataclass
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv('.env')

TOKEN: str = os.getenv('TOKEN')
POSSIBLE_CHARACTERS: str = string.digits + '+-*/. ()'


@dataclass
class Config:
    """Configuration for the bot"""
    channel_id: Optional[int] = None
    current_count: int = 0
    high_score: int = 0
    current_member_id: Optional[int] = None
    put_high_score_emoji: bool = False
    failed_role_id: Optional[int] = None
    reliable_counter_role_id: Optional[int] = None
    failed_member_id: Optional[int] = None
    correct_inputs_by_failed_member: int = 0

    @staticmethod
    def read():
        _config: Optional[Config] = None
        try:
            with open("config.json", "r") as file:
                _config = Config(**json.load(file))
        except FileNotFoundError:
            _config = Config()
            _config.dump_data()
        return _config

    def dump_data(self) -> None:
        """Update the config.json file"""
        with open("config.json", "w", encoding='utf-8') as file:
            json.dump(self.__dict__, file, indent=2)

    def increment(self, member_id: int) -> None:
        """
        Increment the current count.
        NOTE: config is no longer dumped by default. Explicitly call config.dump().
        """
        # increment current count
        self.current_count += 1

        # update current member id
        self.current_member_id = member_id

        # check the high score
        self.high_score = max(self.high_score, self.current_count)

    def reset(self) -> None:
        """
        Reset current count.
        NOTE: config is no longer dumped by default. Explicitly call config.dump_data().
        """
        self.current_count = 0

        self.correct_inputs_by_failed_member = 0

        # update current member id
        self.current_member_id = None
        self.put_high_score_emoji = False

    def reaction_emoji(self) -> str:
        """
        Get the reaction emoji based on the current count.
        NOTE: Data is no longer dumped automatically. Explicitly call config.data_dump().
        """
        if self.current_count == self.high_score and not self.put_high_score_emoji:
            emoji = "🎉"
            self.put_high_score_emoji = True  # Needs a config data dump
        elif self.current_count == 100:
            emoji = "💯"
        elif self.current_count == 69:
            emoji = "😏"
        elif self.current_count == 666:
            emoji = "👹"
        else:
            emoji = "✅"
        return emoji


class Bot(commands.Bot):
    """Counting Discord bot for Indently discord server."""

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        self._config: Config = Config.read()
        self._busy: int = 0
        self._participating_users: Optional[set[int]] = None
        self.failed_role: Optional[discord.Role] = None
        self.reliable_role: Optional[discord.Role] = None
        super().__init__(command_prefix='!', intents=intents)

    def read_config(self):
        """
        Force re-reading the config from the json to the instance variable.
        Mostly for use by slash command functions after they have changed the config values.
        """
        self._config = Config.read()

    async def on_ready(self) -> None:
        """Override the on_ready method"""
        print(f'Bot is ready as {self.user.name}#{self.user.discriminator}')

        busy_work_necessary: bool = False

        if self._config.channel_id:

            channel: Optional[discord.TextChannel] = bot.get_channel(self._config.channel_id)
            if channel:  # It is possible that the channel was removed, so check if channel exists

                emb: discord.Embed = discord.Embed(description=':green_circle:  **I\'m now online!**',
                                                   colour=discord.Color.brand_green())

                if self._config.high_score > 0:
                    emb.description += (f'\n\n:fire:  Let\'s beat the high score of {self._config.high_score}!  '
                                        f':muscle:\n')

                emb.add_field(name='CURRENT number', value=f'{self._config.current_count}', inline=True)

                if self._config.current_member_id:

                    member: Optional[discord.Member] = channel.guild.get_member(self._config.current_member_id)
                    if member:  # It is possible that the member has left the server, so check if member exists
                        emb.add_field(name='Last input by', value=f'{member.mention}', inline=True)

                    else:  # Member has left the server.
                        self._config.current_member_id = None
                        emb.add_field(name='Last input by', value=f'An ex-member', inline=True)
                        busy_work_necessary = True

                await channel.send(embed=emb)

            else:  # Counting channel doesn't exist.
                self._config.channel_id = None
                busy_work_necessary = True

        self.set_roles()

        if busy_work_necessary:
            await self.do_busy_work()

    def set_roles(self):
        """
        Sets the `self.failed_role` and `self.reliable_counter_role` variables.
        """
        for member in self.get_all_members():
            guild: discord.Guild = member.guild

            # Set self.failed_role
            if self._config.failed_role_id is not None:
                self.failed_role = discord.utils.get(guild.roles, id=self._config.failed_role_id)
            else:
                self.failed_role = None

            # Set self.reliable_counter_role
            if self._config.reliable_counter_role_id is not None:
                self.reliable_role = discord.utils.get(guild.roles, id=self._config.reliable_counter_role_id)
            else:
                self.reliable_role = None

            break

    async def add_remove_reliable_role(self):
        """
        Adds/removes the reliable role from participating users.

        Criteria for getting the reliable role:
        1. Accuracy must be > 99%. (Accuracy = correct / (correct + wrong))
        2. Must have score >= 100.
        """
        if self.reliable_role and self._participating_users:

            conn: sqlite3.Connection = sqlite3.connect('database.sqlite3')
            cursor: sqlite3.Cursor = conn.cursor()

            # Make a copy of the set to prevent runtime errors if the set changes while execution
            users: set[int] = self._participating_users.copy()
            self._participating_users = None

            if len(users) == 1:
                sql_stmt: str = f'SELECT member_id, correct, wrong FROM members WHERE member_id = {tuple(users)[0]}'
            else:
                sql_stmt: str = f'SELECT member_id, correct, wrong FROM members WHERE member_id IN {tuple(users)}'

            cursor.execute(sql_stmt)
            result: Optional[list[tuple[int]]] = cursor.fetchall()
            conn.close()

            if result:
                for data in result:
                    member: Optional[discord.Member] = self.reliable_role.guild.get_member(data[0])
                    if member:
                        accuracy: float = (data[1] / (data[1] + data[2])) * 100

                        if float(f'{accuracy:.2f}') >= 99.00 and data[1] - data[2] >= 100:
                            await member.add_roles(self.reliable_role)
                        else:
                            await member.remove_roles(self.reliable_role)

    async def add_remove_failed_role(self):
        """
        Adds the `self.failed_role` to the user whose id is stored in `self._config.failed_member_id`.
        Removes the failed role from all other users.
        Does not proceed if failed role has not been set.
        If `self.failed_role` is not `None` but `self._config.failed_member_id` is `None`, then simply removes
        the failed role from all members who have it currently.
        """
        if self.failed_role:
            handled_member: bool = False

            for member in self.failed_role.members:
                # Iterate through members who have the failed role, and remove those who have not failed

                if self._config.failed_member_id and self._config.failed_member_id == member.id:
                    # Current failed member already has the failed role, so just continue
                    handled_member = True
                    continue
                else:
                    # Either failed_member_id is None, or this member is not the current failed member.
                    # In either case, we have to remove the role.
                    await member.remove_roles(self.failed_role)

            if not handled_member and self._config.failed_member_id:
                # Current failed member does not yet have the failed role
                try:
                    failed_member: discord.Member = await self.failed_role.guild.fetch_member(self._config.failed_member_id)
                    await failed_member.add_roles(self.failed_role)
                except discord.NotFound:
                    # Member is no longer in the server
                    self._config.failed_member_id = None
                    self._config.correct_inputs_by_failed_member = 0
                    self._config.dump_data()

    async def schedule_busy_work(self):
        await asyncio.sleep(5)
        self._busy -= 1
        await self.do_busy_work()

    async def do_busy_work(self):
        if self._busy == 0:
            self._config.dump_data()
            await self.add_remove_failed_role()
            await self.add_remove_reliable_role()

    async def on_message(self, message: discord.Message) -> None:
        """Override the on_message method"""
        if message.author == self.user:
            return

        # Check if the message is in the channel
        if message.channel.id != self._config.channel_id:
            return

        content: str = message.content
        if not all(c in POSSIBLE_CHARACTERS for c in content) or not any(char.isdigit() for char in content):
            return

        zero_division: bool = False

        try:
            number: int = round(eval(content))
        except SyntaxError:
            await message.add_reaction('⚠️')
            await message.channel.send(f'Syntax error in mathematical expression!\nThe chain has **not** been broken.')
            return
        except ZeroDivisionError:
            zero_division = True

        self._busy += 1

        if self._participating_users is None:
            self._participating_users = {message.author.id, }
        else:
            self._participating_users.add(message.author.id)

        conn = sqlite3.connect('database.sqlite3')
        c = conn.cursor()
        c.execute(f'SELECT highest_valid_count FROM members WHERE member_id = {message.author.id}')
        stats: Optional[tuple[int]] = c.fetchone()

        if stats is None:
            highest_valid_count = 0
            c.execute(f'INSERT INTO members VALUES({message.author.id}, 0, 0, 0, 0)')
            conn.commit()
        else:
            highest_valid_count = stats[0]

        # -------------
        # Wrong member
        # -------------
        if zero_division or (self._config.current_count and self._config.current_member_id == message.author.id):

            if self.failed_role:
                self._config.failed_member_id = message.author.id  # Designate current user as failed member
                # Adding/removing failed role is done when not busy

            await self.handle_wrong_member(message)

            c.execute('UPDATE members SET score = score - 1, wrong = wrong + 1 WHERE member_id = ?',
                      (message.author.id,))
            conn.commit()
            conn.close()

            await self.schedule_busy_work()
            return

        # --------------
        # Wrong number
        # --------------
        if int(number) != int(self._config.current_count) + 1:

            if self.failed_role:
                self._config.failed_member_id = message.author.id  # Designate current user as failed member
                # Adding/removing failed role is done when not busy

            await self.handle_wrong_count(message)

            c.execute('UPDATE members SET score = score - 1, wrong = wrong + 1 WHERE member_id = ?',
                      (message.author.id,))

            conn.commit()
            conn.close()

            await self.schedule_busy_work()

            return

        # --------------------
        # Everything is fine
        # ---------------------
        self._config.increment(message.author.id)  # config dump triggered at the end of the method

        await message.add_reaction(self._config.reaction_emoji())  # config dumping done at the end of the method

        c.execute(f'''UPDATE members SET score = score + 1,
correct = correct + 1
{f", highest_valid_count  = {number}" if number > highest_valid_count else ""}
WHERE member_id = ?''',
                  (message.author.id,))
        conn.commit()
        conn.close()

        # Check and reset the self._config.failed_member_id to None.
        # No need to remove the role itself, it will be done later when not busy
        if self.failed_role and self._config.failed_member_id == message.author.id:
            self._config.correct_inputs_by_failed_member += 1
            if self._config.correct_inputs_by_failed_member >= 30:
                self._config.failed_member_id = None
                self._config.correct_inputs_by_failed_member = 0

        await self.schedule_busy_work()

    async def handle_wrong_count(self, message: discord.Message) -> None:
        """Handles when someone messes up the count with a wrong number"""
        correct_number: int = self._config.current_count + 1

        self._config.reset()  # config dump is triggered in on_message

        await message.channel.send(f'''{message.author.mention} messed up the count! \
The correct number was {correct_number}.
Restart from **1** and try to beat the current high score of **{self._config.high_score}**!''')
        await message.add_reaction('❌')

    async def handle_wrong_member(self, message: discord.Message) -> None:
        """Handles when someone messes up the count by counting twice"""

        self._config.reset()  # config dump is triggered in on_message

        await message.channel.send(f'''{message.author.mention} messed up the count! \
You cannot count two numbers in a row!
Restart from **1** and try to beat the current high score of **{self._config.high_score}**!''')
        await message.add_reaction('❌')

    async def on_message_delete(self, message: discord.Message) -> None:
        """Post a message in the channel if a user deletes their input."""

        if not self.is_ready():
            return
        if message.author == self.user:
            return
        if message.channel.id != self._config.channel_id:
            return

        # Check if the deleted message was a legal message
        if not all(c in POSSIBLE_CHARACTERS for c in message.content):
            # The deleted message was not a legal message.
            # But, it is possible that this message was edited prior to deletion,
            # and the original message could have been a legal number.
            # If so, the bot would have reacted to it in some way (tick or cross, we don't care).
            # So we iterate through the reactions and check if any of those had been
            # added by this bot.
            dont_return: bool = False
            if message.reactions:
                for reaction in message.reactions:
                    if reaction.me:
                        # We found a reaction that was posted by this bot.
                        # => this message was a legal message in the past.
                        # Therefore, we need to show a deletion alert.
                        dont_return = True
                        break
            if not dont_return:
                # No reactions were found under the message that were posted
                # by this bot. So we can safely ignore the message.
                return

        await message.channel.send(
            f'{message.author.mention} deleted their number!\n'
            f'Please note that deleting numbers is **prohibited**, even if it has messed up the count. Repeated '
            f'violation of this policy will force the Mods to revoke your access the counting channel permanently.\n\n'
            f'The **NEXT** number is **{self._config.current_count + 1}**.')

    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        """Send a message in the channel if a user modifies their input."""

        if not self.is_ready():
            return
        if before.author == self.user:
            return
        if before.channel.id != self._config.channel_id:
            return

        # Check whether the original message or the edited message are
        # legal messages. If either of those is a legal message,
        # we need to show an alert. No need to check for reactions.
        if not (all(c in POSSIBLE_CHARACTERS for c in before.content)
                or all(c in POSSIBLE_CHARACTERS for c in after.content)):
            return

        if before.content == after.content:
            return

        await after.channel.send(
            f'{after.author.mention} edited their number! {before.jump_url}\n'
            f'Please note that editing numbers is **prohibited**, even if it has messed up the count. Repeated '
            f'violation of this policy will force the Mods to revoke your access the counting channel permanently.\n\n'
            f'The **NEXT** number is **{self._config.current_count + 1}**.')

    async def setup_hook(self) -> None:
        await self.tree.sync()
        conn = sqlite3.connect('database.sqlite3')
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS members (member_id INTEGER PRIMARY KEY,
                score INTEGER, correct INTEGER, wrong INTEGER,
                highest_valid_count INTEGER)''')
        conn.commit()
        conn.close()


bot = Bot()


@bot.tree.command(name='sync', description='Syncs the slash commands to the bot')
@app_commands.default_permissions(administrator=True, ban_members=True)
async def sync(interaction: discord.Interaction):
    """Sync all the slash commands to the bot"""
    if not interaction.user.guild_permissions.ban_members:
        await interaction.response.send_message('You do not have permission to do this!')
        return
    await interaction.response.defer()
    await bot.tree.sync()
    await interaction.followup.send('Synced!')


@bot.tree.command(name='set_channel', description='Sets the channel to count in')
@app_commands.describe(channel='The channel to count in')
@app_commands.default_permissions(ban_members=True)
async def set_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    """Command to set the channel to count in"""
    if not interaction.user.guild_permissions.ban_members:
        await interaction.response.send_message('You do not have permission to do this!')
        return
    await interaction.response.defer()
    config = Config.read()
    config.channel_id = channel.id
    config.dump_data()
    bot.read_config()  # Explicitly ask the bot to re-read the config
    await interaction.followup.send(f'Counting channel was set to {channel.mention}')


@bot.tree.command(name='list_commands', description='Lists commands')
@app_commands.describe(ephemeral='Whether the output should be ephemeral')
async def list_commands(interaction: discord.Interaction, ephemeral: bool = True):
    """Command to list all the slash commands"""
    emb = discord.Embed(title='Slash Commands', color=discord.Color.blue(),
                        description='''
**list_commands** - Lists all the slash commands
**stats_user** - Shows the stats of a specific user
**stats_server** - Shows the stats of the server
**leaderboard** - Shows the leaderboard of the server''')

    if interaction.user.guild_permissions.ban_members:
        emb.description += '''\n
__Restricted commands__ (Admin-only)
**sync** - Syncs the slash commands to the bot
**set_channel** - Sets the channel to count in
**set_failed_role** - Sets the role to give when a user fails
**set_reliable_role** - Sets the reliable role
**remove_failed_role** - Unsets the role to give when a user fails
**remove_reliable_role** - Unsets the reliable role
**force_dump** - Forcibly dump bot config data. Use only when no one is actively playing.
**prune** - Remove data for users who are no longer in the server.
'''

    await interaction.response.send_message(embed=emb, ephemeral=ephemeral)


@bot.tree.command(name='stats_user', description='Shows the user stats')
@app_commands.describe(member='The member to get the stats for')
async def stats_user(interaction: discord.Interaction, member: discord.Member = None):
    """Command to show the stats of a specific user"""
    await interaction.response.defer()

    if member is None:
        member = interaction.user

    emb = discord.Embed(title=f'{member.display_name}\'s stats', color=discord.Color.blue())

    conn = sqlite3.connect('database.sqlite3')
    c = conn.cursor()

    c.execute('SELECT * FROM members WHERE member_id = ?', (member.id,))
    stats = c.fetchone()

    if stats is None:
        await interaction.followup.send('You have never counted in this server!')
        conn.close()
        return

    c.execute(f'SELECT COUNT(member_id) FROM members WHERE score >= {stats[1]}')
    position = c.fetchone()[0]
    conn.close()

    emb.description = f'''{member.mention}\'s stats:\n
**Score:** {stats[1]} (#{position})
**✅Correct:** {stats[2]}
**❌Wrong:** {stats[3]}
**Highest valid count:** {stats[4]}\n
**Accuracy:** {(stats[2] / (stats[2] + stats[3])) * 100:.2f}%'''

    await interaction.followup.send(embed=emb)


@bot.tree.command(name="stats_server", description="View server counting stats")
async def stats_server(interaction: discord.Interaction):
    """Command to show the stats of the server"""
    await interaction.response.defer()

    # Use the bot's config variable, do not re-read file as it may not have been updated yet
    config: Config = bot._config

    if config.channel_id is None:  # channel not set yet
        await interaction.followup.send("Counting channel not set yet!")
        return

    server_stats_embed = discord.Embed(description=f'''**Current Count**: {config.current_count}
High Score: {config.high_score}
{f"Last counted by: <@{config.current_member_id}>" if config.current_member_id else ""}''',
        color=discord.Color.blurple()
    )
    server_stats_embed.set_author(name=interaction.guild, icon_url=interaction.guild.icon)

    await interaction.followup.send(embed=server_stats_embed)


@bot.tree.command(name='leaderboard', description='Shows the first 10 users with the highest score')
async def leaderboard(interaction: discord.Interaction):
    """Command to show the top 10 users with the highest score in Indently"""
    await interaction.response.defer()

    emb = discord.Embed(title='Top 10 users in Indently',
                        color=discord.Color.blue(), description='')

    conn = sqlite3.connect('database.sqlite3')
    c = conn.cursor()
    c.execute('SELECT member_id, score FROM members ORDER BY score DESC LIMIT 10')
    users = c.fetchall()

    for i, user in enumerate(users, 1):
        user_obj = await interaction.guild.fetch_member(user[0])
        emb.description += f'{i}. {user_obj.mention} **{user[1]}**\n'
    conn.close()

    await interaction.followup.send(embed=emb)


@bot.tree.command(name='set_failed_role',
                  description='Sets the role to be used when a user fails to count')
@app_commands.describe(role='The role to be used when a user fails to count')
@app_commands.default_permissions(ban_members=True)
async def set_failed_role(interaction: discord.Interaction, role: discord.Role):
    """Command to set the role to be used when a user fails to count"""
    await interaction.response.defer()
    config = Config.read()
    config.failed_role_id = role.id
    config.dump_data()
    bot.read_config()  # Explicitly ask the bot to re-read the config
    bot.set_roles()  # Ask the bot to re-load the roles
    await interaction.followup.send(f'Failed role was set to {role.mention}.')


@bot.tree.command(name='set_reliable_role',
                  description='Sets the role to be used when a user gets 100 of score')
@app_commands.describe(role='The role to be used when a user fails to count')
@app_commands.default_permissions(ban_members=True)
async def set_reliable_role(interaction: discord.Interaction, role: discord.Role):
    """Command to set the role to be used when a user gets 100 of score"""
    await interaction.response.defer()
    config = Config.read()
    config.reliable_counter_role_id = role.id
    config.dump_data()
    bot.read_config()  # Explicitly ask the bot to re-read the config
    bot.set_roles()  # Ask the bot to re-load the roles
    await interaction.followup.send(f'Reliable role was set to {role.mention}.')


@bot.tree.command(name='remove_failed_role', description='Removes the failed role feature')
@app_commands.default_permissions(ban_members=True)
async def remove_failed_role(interaction: discord.Interaction):
    await interaction.response.defer()
    config = Config.read()
    config.failed_role_id = None
    config.failed_member_id = None
    config.correct_inputs_by_failed_member = 0
    config.dump_data()
    bot.read_config()  # Explicitly ask the bot to re-read the config
    bot.set_roles()  # Ask the bot to re-load the roles
    await interaction.followup.send('Failed role removed.')


@bot.tree.command(name='remove_reliable_role', description='Removes the reliable role feature')
@app_commands.default_permissions(ban_members=True)
async def remove_reliable_role(interaction: discord.Interaction):
    await interaction.response.defer()
    config = Config.read()
    config.reliable_counter_role_id = None
    config.dump_data()
    bot.read_config()  # Explicitly ask the bot to re-read the config
    bot.set_roles()  # Ask the bot to re-load the roles
    await interaction.followup.send('Reliable role removed.')


@bot.tree.command(name='disconnect', description='Makes the bot go offline')
@app_commands.default_permissions(ban_members=True)
async def disconnect(interaction: discord.Interaction):
    emb: discord.Embed = discord.Embed(description=':octagonal_sign:  The bot is going offline  :octagonal_sign:',
                                       colour=discord.Colour.brand_red())
    await interaction.response.send_message(embed=emb)
    await bot.close()


@bot.tree.command(name='force_dump', description='Forcibly dumps configuration data')
@app_commands.default_permissions(ban_members=True)
async def force_dump(interaction: discord.Interaction):
    await interaction.response.defer()
    bot._busy = 0
    await bot.do_busy_work()
    emb = discord.Embed(description=f'✅ Configuration data successfully dumped.', colour=discord.Colour.og_blurple())
    await interaction.followup.send(embed=emb)


@bot.tree.command(name='prune', description='(DANGER) Deletes data of users who are no longer in the server')
@app_commands.default_permissions(ban_members=True)
async def prune(interaction: discord.Interaction):
    await interaction.response.defer()

    conn: sqlite3.Connection = sqlite3.connect('database.sqlite3')
    cursor: sqlite3.Cursor = conn.cursor()

    cursor.execute('SELECT member_id FROM members')
    result: Optional[list[tuple[int]]] = cursor.fetchall()

    if result:
        count: int = 0

        for res in result:
            user_id: int = res[0]

            if interaction.guild.get_member(user_id) is None:
                cursor.execute(f'DELETE FROM members WHERE member_id = {user_id}')
                count += 1
                print(f'Removed data for user {user_id}.')

        if count > 0:
            conn.commit()
            await interaction.followup.send(f'Successfully removed data for {count} user(s).')
        else:
            await interaction.followup.send('No users met the criteria to be removed.')

    else:
        await interaction.followup.send('No users found in the database.')

    conn.close()


@bot.tree.command(name='calc', description='Evaluate a mathematical expression')
@app_commands.describe(expression='The mathematical expression to be evaluated')
async def calc(interaction: discord.Interaction, expression: str) -> None:
    await interaction.response.defer()

    emb: discord.Embed = discord.Embed(description='')

    if not all(c in POSSIBLE_CHARACTERS for c in expression) or not any(char.isdigit() for char in expression):
        emb.description = f'**Expression:** `{expression}`\n\n❌ Invalid mathematical expression!'
        emb.colour = discord.Colour.brand_red()
        await interaction.followup.send(embed=emb)
        return

    try:
        number: int = round(eval(expression))
        emb.description = f'**Expression:** `{expression}`\n\n**Result:** `{number}`'
        emb.colour = discord.Colour.brand_green()
        await interaction.followup.send(embed=emb)
    except SyntaxError:
        emb.description = f'**Expression:** `{expression}`\n\n❌ Invalid mathematical expression!'
        emb.colour = discord.Colour.brand_red()
        await interaction.followup.send(embed=emb)
        return
    except ZeroDivisionError:
        emb.description = f'**Expression:** `{expression}`\n\n❌ Division by zero!'
        emb.colour = discord.Colour.brand_red()
        await interaction.followup.send(embed=emb)
        return

if __name__ == '__main__':
    bot.run(TOKEN)
