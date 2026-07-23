@bot.tree.command(name="serverinfo", description="Retrieves comprehensive analytical data regarding the current guild")
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    embed = discord.Embed(title=f"Guild Specifications: {guild.name}", color=0x00a8fc)
    embed.add_field(name="Identification Key", value=guild.id, inline=True)
    embed.add_field(name="Administrative Owner", value=guild.owner, inline=True)
    embed.add_field(name="Total Membership", value=guild.member_count, inline=True)
    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="purge", description="Executes a bulk deletion of a specified quantity of recent messages")
@app_commands.describe(limit="The explicit quantity of messages to terminate from the channel history")
@app_commands.checks.has_permissions(manage_messages=True)
async def purge(interaction: discord.Interaction, limit: int):
    if limit < 1 or limit > 100:
        await interaction.response.send_message("Operational limit exceeded: Value must range strictly between 1 and 100.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=limit)
    await interaction.followup.send(f"Operation successful: Terminated {len(deleted)} message entries.")

@bot.tree.command(name="coinflip", description="Executes a binary randomized determination algorithm")
async def coinflip(interaction: discord.Interaction):
    outcome = random.choice(["Heads", "Tails"])
    await interaction.response.send_message(f"🪙 Algorithmic determination result: **{outcome}**")
