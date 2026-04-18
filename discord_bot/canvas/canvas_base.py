"""Base classes for Canvas UI components."""

import discord


class CanvasModal(discord.ui.Modal):
    """Base class for Canvas modals with author_id restriction."""

    def __init__(self, author_id: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Restrict the modal to the original Canvas author."""
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ This Canvas menu belongs to another user.", ephemeral=True)
            return False
        return True
