
# Global Button Classes for Persistence and Logic Sharing
class APITicketButton(discord.ui.Button):
    def __init__(self, panel_id, category, label, style, emoji, custom_id):
        super().__init__(label=label, style=style, emoji=emoji, custom_id=custom_id)
        self.panel_id, self.category = panel_id, category
    
    async def callback(self, interaction: discord.Interaction):
        print(f"[DEBUG] APITicketButton Clicked: {self.custom_id}")
        if interaction.response.is_done(): 
            print("[DEBUG] Interaction response already done.")
            return

        cog = interaction.client.get_cog("TicketSetup")
        if not cog:
            # Fallback if case sensitivity issue
            cog = interaction.client.get_cog("TicketSetup") # Try again? No
            # Check loaded cogs
            # print(f"[DEBUG] Loaded cogs: {interaction.client.cogs.keys()}") 
            pass

        if cog: 
            print("[DEBUG] TicketSetup Cog found. Creating ticket...")
            await cog.create_ticket(interaction, self.panel_id, self.category)
        else: 
            print("[ERROR] TicketSetup Cog NOT FOUND.")
            await interaction.response.send_message("Ticket system offline (Cog not loaded).", ephemeral=True)

class APITicketSelect(discord.ui.Select):
    def __init__(self, panel_id, options, custom_id, placeholder):
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options, custom_id=custom_id)
        self.panel_id = panel_id
    
    async def callback(self, interaction: discord.Interaction):
        print(f"[DEBUG] APITicketSelect Changed: {self.values}")
        if interaction.response.is_done(): return
        
        cog = interaction.client.get_cog("TicketSetup")
        if cog:
            self.placeholder = "Select category..."
            await cog.create_ticket(interaction, self.panel_id, self.values[0])
        else: 
            await interaction.response.send_message("Ticket system offline.", ephemeral=True)
