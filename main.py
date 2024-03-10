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
    channel_id: Optional[int]
    current_count: int
    high_score: int
    current_member_id: Optional[int]
    put_high_score_emoji: bool
    failed_role_id: Optional[int]
    reliable_counter_role_id: Optional[int]
    failed_member_id: Optional[int]

    def read():
        with open("config.json", "r") as file:
            config = Config(**json.load(file))
        return config

    def update(self) -> None:
        with open("config.json", "w") as file:
            json.dump(self.__dict__, file, indent=2)

    def increment(self, member_id: int):
        # increment current count
        self.current_count += 1

        # update current member id
        self.current_member_id = member_id

        # check the high score
        if self.current_count > self.high_score:
            self.high_score = self.current_count

        self.update()

    def reset(self):
        # reset current count
        self.current_count = 0

        # update current member id
        self.current_member_id = None
        self.put_high_score_emoji = False

        self.update()

    def reaction_emoji(self):
        if self.current_count == self.high_score and not self.put_high_score_emoji:
            emoji = "🎉"
            self.put_high_score_emoji = True
            self.update()
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
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)

    async def on_ready(self):
        print(f'Bot is ready as {self.user.name}#{self.user.discriminator}')
    
    async def on_message(self, message: discord.Message) -> None:
        if not self.is_ready():
            return

        if message.author == self.user:
            return

        config = Config.read()

        # Check if the message is in the channel
        if message.channel.id != config.channel_id:
            return

        content: str = message.content
        if not all(c in POSSIBLE_CHARACTERS for c in content):
            return

        number: int = round(eval(content))

        conn = sqlite3.connect('database.sqlite3')
        c = conn.cursor()
        c.execute('SELECT * FROM members WHERE member_id = ?', (message.author.id,))
        stats = c.fetchone()
        
        if stats is None:
            score = 0
            correct = 0
            wrong = 0
            highest_valid_count = 0
            c.execute('INSERT INTO members VALUES(?, ?, ?, ?, ?)', (message.author.id, score, correct, wrong, highest_valid_count))
            conn.commit()
        else:
            score = stats[1]
            correct = stats[2]
            wrong = stats[3]
            highest_valid_count = stats[4]

        # Wrong number
        if int(number) != int(config.current_count)+1:
            await self.handle_wrong_count(message)
            c.execute('UPDATE members SET score = score - 1, wrong = wrong + 1 WHERE member_id = ?', (message.author.id,))
            conn.commit()
            conn.close()
            return

        # Wrong member
        if config.current_count and config.current_member_id == message.author.id:
            await self.handle_wrong_member(message)
            c.execute('UPDATE members SET score = score - 1, wrong = wrong + 1 WHERE member_id = ?', (message.author.id,))
            conn.commit()
            conn.close()
            return
        
        # Everything is fine
        config.increment(message.author.id)
        c.execute(f'UPDATE members SET score = score + 1, correct = correct + 1{f", highest_valid_count  = {config.current_count}" if config.current_count > highest_valid_count else ""} WHERE member_id = ?',
                  (message.author.id,))
        conn.commit()
        conn.close()
        await message.add_reaction(config.reaction_emoji())
        if config.reliable_counter_role_id is None:
            return
        reliable_counter_role = discord.utils.get(message.guild.roles, id=config.reliable_counter_role_id)
        if score >= 100 and reliable_counter_role not in message.author.roles:
            await message.author.add_roles(reliable_counter_role)
    
    async def handle_wrong_count(self, message: discord.Message) -> None:
        config: Config = Config.read()
        await message.channel.send(f'{message.author.mention} messed up the count! The correct number was {config.current_count + 1}\nRestart by **1** and try to beat the current high score of **{config.high_score}**!')
        await message.add_reaction('❌')
        if config.failed_role_id is None:
            config.reset()
            return
        failed_role: discord.Role = discord.utils.get(message.guild.roles, id=config.failed_role_id)
        if failed_role not in message.author.roles:
            failed_member: discord.Member = await message.guild.fetch_member(config.current_member_id)
            await failed_member.remove_roles(failed_role)
            await message.author.add_roles(failed_role)
        config.reset()

    async def handle_wrong_member(self, message: discord.Message) -> None:
        config: Config = Config.read()
        await message.channel.send(f'{message.author.mention} messed up the count! You cannot count two numbers in a row!\nRestart by **1** and try to beat the current high score of **{config.high_score}**!')
        await message.add_reaction('❌')
        if config.failed_role_id is None:
            config.reset()
            return
        failed_role = discord.utils.get(message.guild.roles, id=config.failed_role_id)
        if failed_role not in message.author.roles:
            failed_member = await message.guild.fetch_member(config.current_member_id)
            await failed_member.remove_roles(failed_role)
            await message.author.add_roles(failed_role)
        config.reset()
    
        
    async def on_message_delete(self, message: discord.Message) -> None:
        if not self.is_ready():
            return

        if message.author == self.user:
            return

        config = Config.read()

        # Check if the message is in the channel
        if message.channel.id != config.channel_id:
            return
        if not message.reactions:
            return
        if not all(c in POSSIBLE_CHARACTERS for c in message.content):
            return
        await message.channel.send(f'{message.author.mention} deleted his number! The current number is **{config.current_count}**.')
    
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if not self.is_ready():
            return

        if before.author == self.user:
            return

        config = Config.read()

        # Check if the message is in the channel
        if before.channel.id != config.channel_id:
            return
        if not before.reactions:
            return
        if not all(c in POSSIBLE_CHARACTERS for c in before.content):
            return
        await after.channel.send(f'{after.author.mention} edited his number! The current number is **{config.current_count}**.')
    
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        if not self.is_ready():
            return

        if reaction.message.author == self.user:
            return

        config = Config.read()

        # Check if the message is in the channel
        if reaction.message.channel.id != config.channel_id:
            return
        
        if not all(c in POSSIBLE_CHARACTERS for c in reaction.message.content):
            return
        
        if user != self.user:
            await reaction.message.channel.send(f'{user.mention} has put a reaction to the message {reaction.message.jump_url}, it isn\' a valid number!', suppress_embeds=True)

    
    async def setup_hook(self) -> None:
        await self.tree.sync()
        conn = sqlite3.connect('database.sqlite3')
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS members (member_id INTEGER PRIMARY KEY, score INTEGER, correct INTEGER, wrong INTEGER, highest_valid_count INTEGER)')
        conn.commit()
        conn.close()

bot = Bot()


@bot.tree.command(name='sync', description='Syncs the slash commands to the bot')
@app_commands.checks.has_permissions(administrator=True, ban_members=True)
async def sync(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.ban_members:
        await interaction.response.send_message('You do not have permission to do this!')
        return
    await interaction.response.defer()
    await bot.tree.sync()
    await interaction.followup.send('Synced!')


@bot.tree.command(name='setchannel', description='Sets the channel to count in')
@app_commands.describe(channel='The channel to count in')
@app_commands.checks.has_permissions(ban_members=True)
async def set_channel(interaction: discord.Interaction, channel:discord.TextChannel):
    if not interaction.user.guild_permissions.ban_members:
        await interaction.response.send_message('You do not have permission to do this!')
        return
    config = Config.read()
    config.channel_id = channel.id
    config.update()
    await interaction.response.send_message(f'Counting channel was set to {channel.mention}')
    
@bot.tree.command(name='listcmds', description='Lists commands')
async def list_commands(interaction: discord.Interaction):
    emb = discord.Embed(title='Slash Commands', color=discord.Color.blue(), description='')
    for command in bot.tree.walk_commands():
        print(command.name)
        emb.description += f'\n**{command.name}** - {command.description}{" (Admins only)" if command.checks else ""}'
    await interaction.response.send_message(embed=emb)


@bot.tree.command(name='stats_user', description='Shows the user stats')
@app_commands.describe(member='The member to get the stats for')
async def stats_user(interaction:discord.Interaction, member: discord.Member = None):
    if member is None:
        member = interaction.user
    await interaction.response.defer()
    emb = discord.Embed(title=f'{member.display_name}\'s stats', color=discord.Color.blue())
    conn = sqlite3.connect('database.sqlite3')
    c = conn.cursor()
    c.execute('SELECT * FROM members WHERE member_id = ?', (member.id,))
    stats = c.fetchone()
    if stats is None:
        await interaction.response.send_message('You have never counted in this server!')
        conn.close()
        return
    c.execute(f'SELECT score FROM members WHERE member_id = {member.id}')
    score = c.fetchone()[0]
    c.execute(f'SELECT COUNT(member_id) FROM members WHERE score >= {score}')
    position = c.fetchone()[0]
    conn.close()
    emb.description = f'{member.mention}\'s stats:\n\n**Score:** {stats[1]} (#{position})\n**✅Correct:** {stats[2]}\n**❌Wrong:** {stats[3]}\n**Highest valid count:** {stats[4]}\n\n**Correct rate:** {stats[1]/stats[2]*100:.2f}%'
    await interaction.followup.send(embed=emb)
    

@bot.tree.command(name="server_stats", description="View server counting stats")
async def server_stats(interaction: discord.Interaction):

    config = Config.read()

    # channel not seted yet
    if config.channel_id is None:
        await interaction.response.send_message("counting channel not setted yet!")
        return


    server_stats_embed = discord.Embed(
        description=f'**Current Count**: {config.current_count}\nHigh Score: {config.high_score}\n{f"Last counted by: <@{config.current_member_id}>" if config.current_member_id else ""}',
        color=discord.Color.blurple()
    )
    server_stats_embed.set_author(name=interaction.guild, icon_url=interaction.guild.icon)

    await interaction.response.send_message(embed=server_stats_embed)


@bot.tree.command(name='leaderboard', description='Shows the first 10 users with the highest score')
async def leaderboard(interaction: discord.Interaction):
    emb = discord.Embed(title='Top 10 users in Indently', color=discord.Color.blue(), description='')
    conn = sqlite3.connect('database.sqlite3')
    c = conn.cursor()
    c.execute('SELECT member_id, score FROM members ORDER BY score DESC LIMIT 10')
    users = c.fetchall()
    for i, user in enumerate(users, 1):
        user_obj = await interaction.guild.fetch_member(user[0])
        emb.description += f'{i}. {user_obj.mention} **{user[1]}**\n'
    conn.close()
    await interaction.response.send_message(embed=emb)

@bot.tree.command(name='set_failed_role', description='Sets the role to be used when a user fails to count')
@app_commands.describe(role='The role to be used when a user fails to count')
@app_commands.checks.has_permissions(ban_members=True)
async def set_failed_role(interaction: discord.Interaction, role: discord.Role):
    config = Config.read()
    config.failed_role_id = role.id
    config.update()
    await interaction.response.send_message(f'Failed role was set to {role.mention}')


@bot.tree.command(name='set_reliable_role', description='Sets the role to be used when a user gets 100 of score')
@app_commands.describe(role='The role to be used when a user fails to count')
@app_commands.checks.has_permissions(ban_members=True)
async def set_failed_role(interaction: discord.Interaction, role: discord.Role):
    config = Config.read()
    config.reliable_counter_role_id = role.id
    config.update()
    await interaction.response.send_message(f'Reliable role was set to {role.mention}')


if __name__ == '__main__':
    bot.run(TOKEN)
