import os
import json
from ast import literal_eval
from dataclasses import dataclass
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

    def reset(self, member_id: int):
        # reset current count
        self.current_count = -1

        # update current member id
        self.current_member_id = member_id

        self.update()

    def reaction_emoji(self):
        if self.current_count > self.high_score:
            emoji = "🎉"
        elif self.current_count == 100:
            emoji = "💯"
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

        # Wrong number
        if int(number) != int(config.current_count)+1:
            await self.handle_wrong_count(message)
            return

        # Wrong member
        if config.current_count and config.current_member_id == message.author.id:
            await self.handle_wrong_member(message)
            return
        
        # Everything is fine
        config.increment(message.author.id)
        await message.add_reaction(config.reaction_emoji())

    async def handle_wrong_count(self, message: discord.Message) -> None:
        config: Config = Config.read()
        await message.channel.send(f'{message.author.mention} messed up the count! The correct number was {config.current_count + 1}\nRestart by 1.')
        await message.add_reaction('❌')
        config.reset(message.author.id)

    async def handle_wrong_member(self, message: discord.Message) -> None:
        config: Config = Config.read()
        await message.channel.send(f'{message.author.mention} messed up the count! You cannot count two numbers in a row!\nRestart by 1.')
        await message.add_reaction('❌')
        config.reset(message.author.id)
        
    
    async def setup_hook(self) -> None:
        await self.tree.sync()

bot = Bot()


@bot.command()
@commands.has_permissions(ban_members=True)
async def sync(ctx: commands.Context):
    await bot.tree.sync()
    await ctx.send('Synced!')


@bot.tree.command(name='setchannel', description='Sets the channel to count in')
@app_commands.describe(channel='The channel to count in')
async def set_channel(interaction: discord.Interaction, channel:discord.TextChannel):
    if interaction.user.guild_permissions.ban_members:
        await interaction.response.send_message('You do not have permission to do this!')
        return
    config = Config.read()
    config.channel_id = channel.id
    config.update()
    await interaction.response.send_message(f'Counting channel was set to {channel.mention}')
    


if __name__ == '__main__':
    bot.run(TOKEN)