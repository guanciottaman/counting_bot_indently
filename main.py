import os
import json

from dotenv import load_dotenv
import discord
from discord.ext import commands
from discord import app_commands

load_dotenv('.env')

TOKEN: str = os.getenv('TOKEN')
with open('config.json', 'r') as f:
    channel_id = json.load(f)['channel_id']
current_count: int = 0
current_member: discord.Member = None

class Bot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)

    async def on_ready(self):
        print(f'Bot is ready as {self.user.name}#{self.user.discriminator}')
    
    async def on_message(self, message: discord.Message) -> None:
        global current_count
        if message.author == self.user:
            return
        if channel_id is None:
            return
        if message.channel.id != channel_id:
            return
        content: str = message.content.split()[0]
        if not content.isdigit():
            return
        if int(content) != int(content)+1:
            await message.channel.send(f'{message.author.mention} messed up the count! The correct number was {int(content)+1}\nRestart by 0.')
            current_count = 0
            return
        if current_count and current_member == message.author:
            await message.channel.send(f'{message.author.mention} messed up the count! You cannot count two numbers in a row!\nRestart by 0.')
            current_count = 0
            return
        current_count += 1
        if current_count == 100:
            await message.add_reaction(':100:')
        else:
            await message.add_reaction(':white_check_mark:')
    
    async def setup_hook(self) -> None:
        await self.tree.sync()

bot = Bot()


@bot.tree.command(name='setchannel', description='Sets the channel to count in')
@app_commands.describe(channel='The channel to count in')
@commands.has_permissions(ban_members=True)
async def set_channel(ctx: commands.Context, channel:discord.TextChannel):
    if not isinstance(channel_id, int):
        await ctx.send('Channel ID must be an integer')
        return
    with open('config.json', 'w') as f:
        json.dump({'channel_id': channel_id}, f)
    channel: discord.TextChannel = await bot.fetch_channel(channel_id)
    await ctx.send(f'Counting channel was set to {channel.mention}')
    


if __name__ == '__main__':
    bot.run(TOKEN)