import os
import json
from ast import literal_eval
from dataclasses import dataclass
import sqlite3
from typing import Optional

from dotenv import load_dotenv
import discord
from discord.ext import commands
from discord import app_commands

load_dotenv('.env')

TOKEN: str = os.getenv('TOKEN')

@dataclass
class Config:
    channel_id: Optional[int]
    current_count: int
    high_score: int
    current_member_id: Optional[int]
    put_high_score_emoji: bool

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

        content: str = message.content.split()[0]
        if not content.isdigit():
            return

        number: int = literal_eval(content)

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
            score = stats[0]
            correct = stats[1]
            wrong = stats[2]
            highest_valid_count = stats[3]

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
        if config.current_count > highest_valid_count:
            highest_valid_count = config.current_count
        c.execute('UPDATE members SET score = score + 1, correct = correct + 1, highest_valid_count = ? WHERE member_id = ?',
                  (highest_valid_count, message.author.id))
        conn.commit()
        conn.close()
        await message.add_reaction(config.reaction_emoji())

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
        
        if user != self.user:
            await reaction.message.channel.send(f'{user.mention} has put a reaction to the message {reaction.message.jump_url}, it isn\' a valid number!', suppress_embeds=True)

    async def handle_wrong_count(self, message: discord.Message) -> None:
        config: Config = Config.read()
        await message.channel.send(f'{message.author.mention} messed up the count! The correct number was {config.current_count + 1}\nRestart by **1** and try to beat the current high score of **{config.high_score}**!')
        await message.add_reaction('❌')
        config.reset()

    async def handle_wrong_member(self, message: discord.Message) -> None:
        config: Config = Config.read()
        await message.channel.send(f'{message.author.mention} messed up the count! You cannot count two numbers in a row!\nRestart by **1** and try to beat the current high score of **{config.high_score}**!')
        await message.add_reaction('❌')
        config.reset()  
    
    async def setup_hook(self) -> None:
        await self.tree.sync()
        conn = sqlite3.connect('database.sqlite3')
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS members (member_id INTEGER PRIMARY KEY, score INTEGER, correct INTEGER, wrong INTEGER, highest_valid_count INTEGER)')
        conn.commit()
        conn.close()

bot = Bot()


@bot.tree.command(name='sync', description='Syncs the slash commands to the bot')
@app_commands.checks.has_permissions(administrator=True)
async def sync(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.ban_members:
        await interaction.response.send_message('You do not have permission to do this!')
        return
    await interaction.response.defer()
    await bot.tree.sync()
    await interaction.followup.send('Synced!')


@bot.tree.command(name='setchannel', description='Sets the channel to count in')
@app_commands.describe(channel='The channel to count in')
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
    await interaction.response.send_message(bot.commands)


@bot.tree.command(name='userstats', description='Shows the user stats')
@app_commands.describe(member='The member to get the stats for')
async def user_stats(interaction:discord.Interaction, member: discord.Member = None):
    if member is None:
        member = interaction.user
    emb = discord.Embed(title=f'{member.global_name}\'s stats', color=discord.Color.blue())
    conn = sqlite3.connect('database.sqlite3')
    c = conn.cursor()
    c.execute('SELECT * FROM members WHERE member_id = ?', (member.id,))
    stats = c.fetchone()
    print(stats)
    if stats is None:
        await interaction.response.send_message('You have never counted in this server!')
        conn.close()
        return
    c.execute(f'SELECT score FROM members WHERE member_id = {member.id}')
    score = c.fetchone()[0]
    c.execute(f'SELECT COUNT(member_id) FROM members WHERE score >= {score}')
    position = c.fetchone()[0]
    #leaderboard = c.fetchone()
    #print(leaderboard)
    #position = leaderboard.index(member.id) + 1
    emb.description = f'{member.mention}\'s stats:\n\n**Score:** {stats[1]} (#{position})\n**✅Correct:** {stats[2]}\n**❌Wrong:** {stats[3]}\n**Highest valid count:** {stats[4]}\n\n**Correct rate:** {stats[1]/stats[2]*100:.2f}%'
    await interaction.response.send_message(embed=emb)
    conn.close()

@bot.tree.command(name="server_stats", description="View server counting stats")
@app_commands.describe()
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


if __name__ == '__main__':
    bot.run(TOKEN)
