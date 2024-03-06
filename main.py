import os

from dotenv import load_dotenv
import discord
from discord.ext import commands

load_dotenv('.env')

TOKEN: str = os.getenv('TOKEN')

class Bot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=discord.Intents.default())

    async def on_ready(self):
        print(f'Bot is ready as {self.user.name}#{self.user.discriminator}')

bot = Bot()


if __name__ == '__main__':
    bot.run(TOKEN)