import customtkinter as ctk
from tkinter import filedialog, messagebox
import tkinter as tk
import requests, zipfile, shutil, tempfile, os, webbrowser
from PIL import Image, ImageTk
from io import BytesIO

# -------------------------
# CONFIG
# -------------------------
JSON_URL = "https://raw.githubusercontent.com/TS-DEV-DEBUG-V2/steamgamepatcher/refs/heads/main/games.json"

# -------------------------
# GLOBALS
# -------------------------
data = None
games = []
selected_game = None
game_folder = ""

# -------------------------
# LOAD JSON
# -------------------------
def load_json():
    global data, games
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(JSON_URL, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        games = data["games"]
    except Exception as e:
        messagebox.showerror("Error", f"Failed to load JSON\n{e}")

# -------------------------
# IMAGE LOADING
# -------------------------
def load_image(url, size):
    try:
        r = requests.get(url)
        img = Image.open(BytesIO(r.content))
        img = img.resize(size)
        return ImageTk.PhotoImage(img)
    except:
        return None

# -------------------------
# GAME SELECTION
# -------------------------
def select_game(index):
    global selected_game
    selected_game = games[index]
    main_game_name.set(selected_game["name"])

    banner = load_image(selected_game.get("game_banner", ""), (520, 200))
    if banner:
        main_banner_label.configure(image=banner, text="")
        main_banner_label.image = banner
    else:
        main_banner_label.configure(image="", text="No banner available")

    main_instructions_text.configure(state="normal")
    main_instructions_text.delete("0.0", "end")
    main_instructions_text.insert("0.0", selected_game["instructions"])
    main_instructions_text.configure(state="disabled")

# -------------------------
# SEARCH / FILTER
# -------------------------
def filter_games(*args):
    query = search_var.get().lower().strip()
    for row, i in game_rows:
        name = games[i]["name"].lower()
        if query in name:
            row.pack(fill="x", pady=4, padx=4)
        else:
            row.pack_forget()

# -------------------------
# FOLDER SELECT
# -------------------------
def choose_folder():
    global game_folder
    game_folder = filedialog.askdirectory()
    if game_folder:
        folder_label_var.set(game_folder)

# -------------------------
# PATCH GAME
# -------------------------
def patch_game():
    if not selected_game:
        messagebox.showerror("Error", "Select a game")
        return
    if not game_folder:
        messagebox.showerror("Error", "Select game folder")
        return
    try:
        url = selected_game["patch_url"]
        tmp = tempfile.mkdtemp()
        zip_path = os.path.join(tmp, "patch.zip")

        status_var.set("Downloading patch...")
        root.update()

        r = requests.get(url)
        with open(zip_path, "wb") as f:
            f.write(r.content)

        status_var.set("Extracting patch...")
        root.update()

        extract_dir = os.path.join(tmp, "extract")
        os.makedirs(extract_dir, exist_ok=True)
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(extract_dir)

        status_var.set("Installing patch...")
        root.update()

        for walk_root, dirs, files in os.walk(extract_dir):
            rel = os.path.relpath(walk_root, extract_dir)
            dest = os.path.join(game_folder, rel)
            os.makedirs(dest, exist_ok=True)
            for file in files:
                src = os.path.join(walk_root, file)
                dst = os.path.join(dest, file)
                shutil.copy2(src, dst)

        shutil.rmtree(tmp)
        status_var.set("Patch Complete!")
        messagebox.showinfo("Success", "Game patched successfully!")
    except Exception as e:
        messagebox.showerror("Error", str(e))
        status_var.set("Error during patching.")

# -------------------------
# LINKS
# -------------------------
def open_github():
    if data and data.get("github"):
        webbrowser.open(data["github"])

def open_discord():
    if data and data.get("discord"):
        webbrowser.open(data["discord"])

# -------------------------
# SETUP
# -------------------------
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

root = ctk.CTk()
root.title("Steam Game Patcher Pro")
root.geometry("860x600")

# -------------------------
# MENU BAR
# -------------------------
def show_about():
    messagebox.showinfo("About", "Steam Game Patcher Pro\nMade with CustomTkinter")

menu_bar = tk.Menu(root)
file_menu = tk.Menu(menu_bar, tearoff=0)
file_menu.add_command(label="Exit", command=root.destroy)
menu_bar.add_cascade(label="File", menu=file_menu)
help_menu = tk.Menu(menu_bar, tearoff=0)
help_menu.add_command(label="About", command=show_about)
menu_bar.add_cascade(label="Help", menu=help_menu)
root.config(menu=menu_bar)

# -------------------------
# LOAD DATA
# -------------------------
load_json()

# -------------------------
# FOOTER
# -------------------------
footer_frame = ctk.CTkFrame(root, height=50)
footer_frame.pack(side="bottom", fill="x")

github_icon = None
discord_icon = None
if data and data.get("icons"):
    github_icon = load_image(data["icons"].get("github", ""), (32, 32))
    discord_icon = load_image(data["icons"].get("discord", ""), (32, 32))

github_btn = ctk.CTkButton(
    footer_frame,
    image=github_icon if github_icon else None,
    text="" if github_icon else "GitHub",
    width=50,
    command=open_github
)
github_btn.pack(side="left", padx=10, pady=5)

discord_btn = ctk.CTkButton(
    footer_frame,
    image=discord_icon if discord_icon else None,
    text="" if discord_icon else "Discord",
    width=50,
    command=open_discord
)
discord_btn.pack(side="left", padx=10, pady=5)

# -------------------------
# LEFT PANEL
# -------------------------
left_frame = ctk.CTkFrame(root, width=220)
left_frame.pack(side="left", fill="y", padx=10, pady=10)
left_frame.pack_propagate(False)

# Search bar at the top of the left panel
search_var = ctk.StringVar()
search_var.trace_add("write", filter_games)
search_entry = ctk.CTkEntry(
    left_frame,
    textvariable=search_var,
    placeholder_text="🔍  Search games...",
    width=200
)
search_entry.pack(pady=(8, 6), padx=8)

# Scrollable frame for game list so it doesn't overflow with many games
games_scroll = ctk.CTkScrollableFrame(left_frame, fg_color="transparent")
games_scroll.pack(fill="both", expand=True, padx=4, pady=(0, 4))

# Keep logo image references so GC doesn't collect them
sidebar_logos = []
# game_rows stores (row_widget, original_index) so filter_games can show/hide them
game_rows = []

game_buttons = []
for i, g in enumerate(games):
    row = ctk.CTkFrame(games_scroll, fg_color="transparent")
    row.pack(fill="x", pady=4, padx=4)

    logo_img = load_image(g.get("logo", ""), (28, 28))
    sidebar_logos.append(logo_img)

    logo_lbl = ctk.CTkLabel(row, text="", image=logo_img if logo_img else None, width=28, height=28)
    logo_lbl.pack(side="left", padx=(2, 4))

    btn = ctk.CTkButton(
        row,
        text=g["name"],
        anchor="w",
        width=150,
        command=lambda i=i: select_game(i)
    )
    btn.pack(side="left", fill="x", expand=True)
    game_buttons.append(btn)
    game_rows.append((row, i))

# -------------------------
# MAIN PANEL
# -------------------------
main_frame = ctk.CTkFrame(root)
main_frame.pack(side="left", fill="both", expand=True, padx=10, pady=10)

main_game_name = ctk.StringVar(value="Select a game")
game_name_label = ctk.CTkLabel(
    main_frame,
    textvariable=main_game_name,
    font=ctk.CTkFont(size=18, weight="bold")
)
game_name_label.pack(pady=(12, 6))

main_banner_label = ctk.CTkLabel(main_frame, text="", width=520, height=200)
main_banner_label.pack(pady=(0, 8))

folder_label_var = ctk.StringVar(value="No folder selected")
folder_btn = ctk.CTkButton(main_frame, text="Select Game Folder", command=choose_folder)
folder_btn.pack(pady=5)
folder_label = ctk.CTkLabel(main_frame, textvariable=folder_label_var)
folder_label.pack()

instr_label = ctk.CTkLabel(main_frame, text="Instructions:")
instr_label.pack(pady=(10, 0))
main_instructions_text = ctk.CTkTextbox(main_frame, width=400, height=80)
main_instructions_text.pack()
main_instructions_text.configure(state="disabled")

patch_btn = ctk.CTkButton(main_frame, text="PATCH GAME", command=patch_game, width=200)
patch_btn.pack(pady=12)

status_var = ctk.StringVar(value="")
status_label = ctk.CTkLabel(main_frame, textvariable=status_var)
status_label.pack(pady=4)


root.mainloop()
