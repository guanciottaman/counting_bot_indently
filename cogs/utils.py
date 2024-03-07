import sqlite3

import discord
from discord.ext import commands
from discord import app_commands


class Utils(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name='userstats', description='Shows the user stats')
    @app_commands.describe(member='The member to get the stats for')
    async def user_stats(self, interaction:discord.Interaction, member: discord.Member = None):
        if member is None:
            member = interaction.user
        emb = discord.Embed(title=f'{member.global_name}\'s stats', color=discord.Color.blue())
        conn = sqlite3.connect('database.sqlite3')
        c = conn.cursor()
        c.execute('SELECT * FROM members WHERE member_id = ?', (member.id,))
        stats = c.fetchone()
        if stats is None:
            await interaction.response.send_message('You have never counted in this server!')
            conn.close()
            return
        c.execute('SELECT member_id FROM members ORDER BY score DESC')
        leaderboard = c.fetchall()
        position = leaderboard.index(member.id) + 1
        emb.description = f'{member.mention}\'s stats:\n\n**Score:** {stats[0]} (#{position})\n**✅Correct:** {stats[1]}\n**❌Wrong:** {stats[2]}\n**Highest valid count:** {stats[3]}\n\n'
        await interaction.response.send_message(embed=emb)
        conn.close()

    

async def setup(bot: commands.Bot):
    await bot.add_cog(Utils(bot))