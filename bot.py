import discord
from keep_alive import keep_alive
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import json
import datetime
import random
import os

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

tirage_data = {}  # Tirage actuel
user_data = {}    # Données utilisateurs

# Charger les données
def load_data():
    global user_data
    try:
        with open("user_data.json", "r") as f:
            user_data = json.load(f)
    except FileNotFoundError:
        user_data = {}

# Sauvegarder les données
def save_data():
    with open("user_data.json", "w") as f:
        json.dump(user_data, f, indent=4)

@bot.event
async def on_ready():
    load_data()
    await tree.sync()
    print(f"Bot connecté : {bot.user}")

# ==== MODAL INSCRIPTION ====
class TirageModal(discord.ui.Modal, title="Inscription au tirage"):
    pseudo_mc = discord.ui.TextInput(label="Ton pseudo Minecraft")

    async def on_submit(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        if user_id not in user_data:
            user_data[user_id] = {
                "pseudo_mc": self.pseudo_mc.value,
                "points": 5,
                "participations": 0,
                "gagnes": 0
            }
        else:
            user_data[user_id]["pseudo_mc"] = self.pseudo_mc.value

        tirage_data["participants"][user_id] = self.pseudo_mc.value
        user_data[user_id]["participations"] += 1
        save_data()

        await interaction.response.send_message("✅ Tu es bien inscrit au tirage !", ephemeral=True)

# ==== VIEW AVEC BOUTONS ====
class TirageView(discord.ui.View):
    def __init__(self, message, timeout=None):
        super().__init__(timeout=timeout)
        self.message = message

    @discord.ui.button(label="S'inscrire", style=discord.ButtonStyle.success)
    async def inscrire(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TirageModal())
        await self.update_message()

    @discord.ui.button(label="Se désinscrire", style=discord.ButtonStyle.danger)
    async def desinscrire(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id)
        if user_id in tirage_data["participants"]:
            del tirage_data["participants"][user_id]
            await interaction.response.send_message("❌ Tu as été désinscrit du tirage.", ephemeral=True)
            save_data()
        else:
            await interaction.response.send_message("Tu n'es pas inscrit à ce tirage.", ephemeral=True)
        await self.update_message()

    async def update_message(self):
        embed = self.message.embeds[0]
        embed.description = (
            f"🕒 Début à **{datetime.datetime.fromisoformat(tirage_data['heure']).strftime('%H:%M')}**\n"
            f"👥 Joueurs max : **{tirage_data['max_participants']}**\n"
            f"✅ Participants inscrits : `{len(tirage_data['participants'])}`"
        )
        await self.message.edit(embed=embed, view=self)

# ==== COMMANDE /START_TIRAGE ====
@tree.command(name="start_tirage", description="Lancer un tirage au sort")
@app_commands.describe(
    heure="Heure de début au format HH:MM (24h)",
    nom="Nom de la partie",
    nombre="Nombre de participants"
)
async def start_tirage(interaction: discord.Interaction, heure: str, nom: str, nombre: int):
    try:
        heure_obj = datetime.datetime.strptime(heure, "%H:%M").time()
        now = datetime.datetime.now()
        start_time = datetime.datetime.combine(now.date(), heure_obj)
        if start_time < now:
            start_time += datetime.timedelta(days=1)
    except ValueError:
        await interaction.response.send_message("⛔ Format d'heure invalide. Utilise HH:MM.", ephemeral=True)
        return

    tirage_data.clear()
    tirage_data.update({
        "nom": nom,
        "heure": start_time.isoformat(),
        "max_participants": nombre,
        "participants": {}
    })

    embed = discord.Embed(
        title=f"🎯 Tirage au sort : {nom}",
        description=f"🕒 Début à **{heure}**\n👥 Joueurs max : **{nombre}**\n✅ Participants inscrits : `0`",
        color=discord.Color.blue()
    )
    embed.set_footer(text="Clique sur un bouton pour t'inscrire ou te désinscrire.")

    msg = await interaction.channel.send("@LG", embed=embed, view=TirageView(None))
    view = TirageView(msg)
    view.message = msg
    await msg.edit(view=view)

    await interaction.response.send_message("✅ Tirage lancé avec succès !", ephemeral=True)

# ==== COMMANDE /TIRER ====
@tree.command(name="tirer", description="Tirer au sort des gagnants")
@app_commands.describe(nombre="Nombre de gagnants à tirer")
async def tirer(interaction: discord.Interaction, nombre: int):
    if not tirage_data or not tirage_data.get("participants"):
        await interaction.response.send_message("⛔ Aucun tirage actif ou participants vides.", ephemeral=True)
        return

    participants = list(tirage_data["participants"].keys())
    if nombre > len(participants):
        await interaction.response.send_message("⛔ Pas assez de participants.", ephemeral=True)
        return

    # Calcul pondéré par les points
    pool = []
    for user_id in participants:
        points = user_data.get(user_id, {}).get("points", 5)
        pool.extend([user_id] * points)

    winners = set()
    while len(winners) < nombre:
        winners.add(random.choice(pool))

    result = ""
    for user_id in participants:
        if user_id in winners:
            user_data[user_id]["points"] = 1
            user_data[user_id]["gagnes"] += 1
        else:
            user_data[user_id]["points"] += 1

    save_data()

    result = "🎉 **Gagnants du tirage** 🎉\n"
    mc_pseudos = []
    for winner_id in winners:
        member = await interaction.guild.fetch_member(int(winner_id))
        mc = user_data[winner_id]["pseudo_mc"]
        mc_pseudos.append(mc)
        result += f"🏆 {member.mention} - **{mc}**\n"
        await member.send(f"🎉 Tu as gagné le tirage avec ton pseudo Minecraft **{mc}** !")

    await interaction.channel.send(result)
    await interaction.response.send_message("✅ Tirage effectué et gagnants notifiés en MP.", ephemeral=True)

# ==== COMMANDE /ME ====
@tree.command(name="me", description="Voir mes infos de tirage")
async def me(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    if user_id not in user_data:
        await interaction.response.send_message("❌ Tu n'es pas encore inscrit à un tirage.", ephemeral=True)
        return

    data = user_data[user_id]
    embed = discord.Embed(
        title=f"📋 Tes infos",
        description=(
            f"👤 **{interaction.user.display_name}**\n"
            f"🧱 Pseudo Minecraft : `{data['pseudo_mc']}`\n"
            f"⭐ Points : `{data['points']}`"
        ),
        color=discord.Color.green()
    )
    embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else discord.Embed.Empty)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ==== COMMANDE /VERIF ====
@tree.command(name="verif", description="Vérifier un utilisateur")
@app_commands.describe(utilisateur="Utilisateur à vérifier")
async def verif(interaction: discord.Interaction, utilisateur: discord.User):
    user_id = str(utilisateur.id)
    if user_id not in user_data:
        await interaction.response.send_message("❌ Cet utilisateur n'a pas encore participé.", ephemeral=True)
        return

    data = user_data[user_id]
    embed = discord.Embed(
        title=f"🔎 Infos de {utilisateur.name}",
        description=(
            f"🧱 Pseudo Minecraft : `{data['pseudo_mc']}`\n"
            f"⭐ Points : `{data['points']}`\n"
            f"🎯 Participations : `{data['participations']}`\n"
            f"🏆 Victoires : `{data['gagnes']}`"
        ),
        color=discord.Color.orange()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ==== LANCEMENT DU BOT ====
keep_alive()
bot.run(os.getenv("DISCORD_TOKEN"))