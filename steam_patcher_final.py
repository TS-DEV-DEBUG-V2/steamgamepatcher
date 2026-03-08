import customtkinter as ctk
from tkinter import filedialog, messagebox
import tkinter as tk
import requests, zipfile, shutil, tempfile, os, webbrowser
from PIL import Image, ImageTk
from io import BytesIO
import threading
import queue


JSON_URL = "https://raw.githubusercontent.com/TS-DEV-DEBUG-V2/steamgamepatcher/main/games.json"


data = None
games = []
selected_game = None
game_folder = ""
_patch_thread = None  # track active patch thread

# thread-safe queue for UI updates from background threads
ui_queue = queue.Queue()


def process_ui_queue():
    """Drain the queue and apply all pending UI updates on the main thread."""
    try:
        while True:
            fn = ui_queue.get_nowait()
            fn()
    except queue.Empty:
        pass
    root.after(50, process_ui_queue)

def ui(fn):
    """Schedule a callable to run on the main thread via the queue."""
    ui_queue.put(fn)


def load_json():
    """Fetch game list in a daemon thread; populate UI when done."""
    def _fetch():
        global data, games
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            r = requests.get(JSON_URL, headers=headers, timeout=10)
            r.raise_for_status()
            loaded_data = r.json()
            loaded_games = loaded_data["games"]
            ui(lambda: _on_json_loaded(loaded_data, loaded_games))
        except Exception as e:
            ui(lambda: messagebox.showerror("Error", f"Failed to load JSON\n{e}"))

    t = threading.Thread(target=_fetch, daemon=True)
    t.start()

def _on_json_loaded(loaded_data, loaded_games):
    """Called on the main thread once JSON is fetched."""
    global data, games
    data = loaded_data
    games = loaded_games

    # load footer icons now that data is available
    _load_footer_icons()

    # populate game list
    _populate_game_list()

    # clear the loading status
    status_var.set("")


def load_image_async(url, size, callback):
    """Fetch and resize an image in a daemon thread, then call callback(img) on main thread."""
    def _fetch():
        try:
            r = requests.get(url, timeout=10)
            img = Image.open(BytesIO(r.content)).resize(size)
            photo = ImageTk.PhotoImage(img)
            ui(lambda: callback(photo))
        except Exception:
            ui(lambda: callback(None))

    t = threading.Thread(target=_fetch, daemon=True)
    t.start()

def load_image(url, size):
    """Synchronous image loader (kept for small/one-off cases)."""
    try:
        r = requests.get(url, timeout=10)
        img = Image.open(BytesIO(r.content)).resize(size)
        return ImageTk.PhotoImage(img)
    except Exception:
        return None


def select_game(index):
    global selected_game
    selected_game = games[index]
    main_game_name.set(selected_game["name"])

    # reset banner while new one loads
    main_banner_label.configure(image="", text="Loading banner…")

    def _on_banner(photo):
        if photo:
            main_banner_label.configure(image=photo, text="")
            main_banner_label.image = photo  # prevent GC
        else:
            main_banner_label.configure(image="", text="No banner available")

    load_image_async(selected_game.get("game_banner", ""), (520, 200), _on_banner)

    main_instructions_text.configure(state="normal")
    main_instructions_text.delete("0.0", "end")
    main_instructions_text.insert("0.0", selected_game["instructions"])
    main_instructions_text.configure(state="disabled")


def filter_games(*args):
    query = search_var.get().lower().strip()
    for row, i in game_rows:
        name = games[i]["name"].lower()
        if query in name:
            row.pack(fill="x", pady=4, padx=4)
        else:
            row.pack_forget()


def choose_folder():
    global game_folder
    game_folder = filedialog.askdirectory()
    if game_folder:
        folder_label_var.set(game_folder)


def patch_game():
    global _patch_thread
    if not selected_game:
        messagebox.showerror("Error", "Select a game")
        return
    if not game_folder:
        messagebox.showerror("Error", "Select game folder")
        return

    if _patch_thread and _patch_thread.is_alive():
        messagebox.showwarning("Busy", "A patch is already in progress.")
        return

    patch_btn.configure(state="disabled", text="Patching…")
    status_var.set("Starting patch…")
    ui(lambda: _show_progress())

    def _run():
        try:
            url = selected_game["patch_url"]
            tmp = tempfile.mkdtemp()
            zip_path = os.path.join(tmp, "patch.zip")

            # dl with real progress
            ui(lambda: status_var.set("Downloading patch…"))
            ui(lambda: progress_working_var.set("Working…"))

            r = requests.get(url, stream=True, timeout=60)
            r.raise_for_status()

            total = int(r.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 65536  # 64 KB

            with open(zip_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            pct = downloaded / total
                            ui(lambda p=pct: progress_bar.set(p))
                        else:
                            # Unknown size pulse between 0 and 0.95
                            pulse = (downloaded // chunk_size % 20) / 20
                            ui(lambda p=pulse: progress_bar.set(p))

            ui(lambda: progress_bar.set(1.0))

            # Extract
            ui(lambda: status_var.set("Extracting patch…"))
            ui(lambda: progress_bar.set(0))

            extract_dir = os.path.join(tmp, "extract")
            os.makedirs(extract_dir, exist_ok=True)
            with zipfile.ZipFile(zip_path, "r") as z:
                members = z.namelist()
                total_members = len(members)
                for idx, member in enumerate(members, 1):
                    z.extract(member, extract_dir)
                    pct = idx / total_members if total_members else 1
                    ui(lambda p=pct: progress_bar.set(p))

            ui(lambda: progress_bar.set(1.0))

            # install
            ui(lambda: status_var.set("Installing patch…"))
            ui(lambda: progress_bar.set(0))

            all_files = []
            for walk_root, dirs, files in os.walk(extract_dir):
                for file in files:
                    all_files.append((walk_root, file))

            total_files = len(all_files)
            for i, (walk_root, file) in enumerate(all_files, 1):
                rel = os.path.relpath(walk_root, extract_dir)
                dest = os.path.join(game_folder, rel)
                os.makedirs(dest, exist_ok=True)
                shutil.copy2(os.path.join(walk_root, file), os.path.join(dest, file))
                pct = i / total_files if total_files else 1
                ui(lambda p=pct: progress_bar.set(p))

            shutil.rmtree(tmp)
            ui(lambda: _patch_done(success=True))

        except Exception as e:
            err = str(e)
            ui(lambda: _patch_done(success=False, error=err))

    _patch_thread = threading.Thread(target=_run, daemon=True)
    _patch_thread.start()

def _show_progress():
    progress_bar.set(0)
    progress_frame.pack(pady=(0, 4))

def _patch_done(success, error=None):
    patch_btn.configure(state="normal", text="PATCH GAME")
    progress_frame.pack_forget()
    progress_working_var.set("")
    if success:
        status_var.set("Patch Complete!")
        messagebox.showinfo("Success", "Game patched successfully!")
    else:
        status_var.set("Error during patching.")
        messagebox.showerror("Error", error)


def open_github():
    if data and data.get("github"):
        webbrowser.open(data["github"])

def open_discord():
    if data and data.get("discord"):
        webbrowser.open(data["discord"])


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

root = ctk.CTk()
root.title("Steam Game Patcher Pro")
root.geometry("860x625")
root.resizable(False, False)


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


footer_frame = ctk.CTkFrame(root, height=50)
footer_frame.pack(side="bottom", fill="x")

# placeholder buttons (icons loaded async after JSON fetch)
github_btn = ctk.CTkButton(footer_frame, text="GitHub", width=50, command=open_github)
github_btn.pack(side="left", padx=10, pady=5)

discord_btn = ctk.CTkButton(footer_frame, text="Discord", width=50, command=open_discord)
discord_btn.pack(side="left", padx=10, pady=5)

def _load_footer_icons():
    if not (data and data.get("icons")):
        return

    def _set_github(photo):
        if photo:
            github_btn.configure(image=photo, text="")
            github_btn.image = photo

    def _set_discord(photo):
        if photo:
            discord_btn.configure(image=photo, text="")
            discord_btn.image = photo

    load_image_async(data["icons"].get("github", ""), (32, 32), _set_github)
    load_image_async(data["icons"].get("discord", ""), (32, 32), _set_discord)


left_frame = ctk.CTkFrame(root, width=220)
left_frame.pack(side="left", fill="y", padx=10, pady=10)
left_frame.pack_propagate(False)

search_var = ctk.StringVar()
search_var.trace_add("write", filter_games)
search_entry = ctk.CTkEntry(
    left_frame,
    textvariable=search_var,
    placeholder_text="Search games…",
    width=200
)
search_entry.pack(pady=(8, 6), padx=8)

games_scroll = ctk.CTkScrollableFrame(left_frame, fg_color="transparent")
games_scroll.pack(fill="both", expand=True, padx=4, pady=(0, 4))

sidebar_logos = []
game_rows = []
game_buttons = []

def _populate_game_list():
    """Build the game list rows after JSON has been loaded."""
    for i, g in enumerate(games):
        row = ctk.CTkFrame(games_scroll, fg_color="transparent")
        row.pack(fill="x", pady=4, padx=4)

        # Placeholder label while logo loads
        logo_lbl = ctk.CTkLabel(row, text="", width=28, height=28)
        logo_lbl.pack(side="left", padx=(2, 4))
        sidebar_logos.append(None)

        btn = ctk.CTkButton(
            row,
            text=g["name"],
            anchor="w",
            width=150,
            command=lambda idx=i: select_game(idx)
        )
        btn.pack(side="left", fill="x", expand=True)
        game_buttons.append(btn)
        game_rows.append((row, i))

        # Load logo async
        idx = i  # capture
        def _set_logo(photo, lbl=logo_lbl, pos=idx):
            if photo:
                lbl.configure(image=photo)
                lbl.image = photo
                sidebar_logos[pos] = photo

        load_image_async(g.get("logo", ""), (28, 28), _set_logo)


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

# progress bar row (hidden until patching starts)
progress_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
progress_bar = ctk.CTkProgressBar(progress_frame, width=300)
progress_bar.set(0)
progress_bar.pack(side="left", padx=(0, 8))
progress_working_var = ctk.StringVar(value="")
progress_working_label = ctk.CTkLabel(progress_frame, textvariable=progress_working_var)
progress_working_label.pack(side="left")

status_var = ctk.StringVar(value="Loading game list…")
status_label = ctk.CTkLabel(main_frame, textvariable=status_var)
status_label.pack(pady=4)


root.after(50, process_ui_queue)


load_json()

root.mainloop()
