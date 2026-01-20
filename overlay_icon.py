# Copyright 2026 Azikaban/Bob8259

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

import customtkinter as ctk

class OverlayIcon(ctk.CTkToplevel):
    def __init__(self, master, icon_type="start"):
        super().__init__(master)
        self.title("Overlay")
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        
        # Windows transparency trick: use a color key
        # We use a color that is unlikely to be used in the icon itself
        self.attributes("-transparentcolor", "white")
        self.configure(fg_color="white")
        
        size = 120
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width // 2) - (size // 2)
        y = (screen_height // 2) - (size // 2)
        self.geometry(f"{size}x{size}+{x}+{y}")
        
        self.canvas = ctk.CTkCanvas(self, width=size, height=size, bg="white", highlightthickness=0)
        self.canvas.pack(expand=True, fill="both")
        
        if icon_type == "start":
            # Green Play Triangle
            self.canvas.create_polygon([30, 20, 30, 100, 100, 60], fill="#27ae60", outline="#2ecc71", width=2)
        elif icon_type == "pause":
            # Orange Pause Bars
            self.canvas.create_rectangle(35, 25, 55, 95, fill="#e67e22", outline="#d35400", width=2)
            self.canvas.create_rectangle(65, 25, 85, 95, fill="#e67e22", outline="#d35400", width=2)
            
        self.after(1000, self.destroy)
