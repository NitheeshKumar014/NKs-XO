# X-O Arena

A small, local two-player X-O (tic-tac-toe) game built with Flask and Flask-SocketIO. The server keeps room and board state in memory and validates room joins and moves.

Each player's turn has a server-enforced 60-second clock. Wins, losses, timeout losses, and draws have different result animations. Rooms keep a best-of-three scoreboard: the first player to two wins takes the series; draws award no point, and an equal score after three rounds is a series draw. The starting symbol switches between rounds.

## What you need

- Python 3.10 or newer
- VS Code (recommended) or another terminal
- Internet access during setup to download Python packages, and when opening the page because the Socket.IO browser client and optional display fonts load from public CDNs

## Open in VS Code

1. Extract the ZIP file.
2. In VS Code, choose **File → Open Folder…** and select the extracted **XO_Arena** folder (the folder containing **app.py**).
3. Open **Terminal → New Terminal**.

## Install and run on Windows PowerShell

Run these commands from the XO_Arena folder:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python app.py
```

If **py -3** is unavailable, use **python -m venv .venv**. If PowerShell blocks the activation script, open a Command Prompt terminal and activate with **.venv\Scripts\activate.bat**, then continue with the same pip commands.

## Install and run on macOS or Linux

Run these commands from the XO_Arena folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python app.py
```

## Open the game

Keep the terminal running and open **http://127.0.0.1:5000** in your browser. Use **Create a room** in one browser and enter its six-character code in a second browser to join.

To stop the server, focus the terminal and press **Ctrl+C**.

## Local network note

By default, the server listens only on your computer (127.0.0.1). To play from a phone or another device, connect it to the same trusted Wi-Fi network, set HOST=0.0.0.0 before starting the app, and open the computer's LAN IP address on the device, for example http://192.168.1.20:5000. In PowerShell, use **$env:HOST="0.0.0.0"** before **python app.py**; on macOS/Linux, use **HOST=0.0.0.0 python app.py**. A firewall may need to allow the connection. This is still a local development server.

## Share a public link with friends (Render)

The `render.yaml` file prepares this project for a small hobby deployment on Render. This gives you an HTTPS link that friends can open from different networks. You need a GitHub account and a Render account to deploy it:

1. Create a GitHub repository for this project and upload the contents of the **XO_Arena** folder. Keep the repository private if you only want invited collaborators to see the source code; the deployed game link itself is public to anyone who has it.
2. Sign in to Render and choose **New → Blueprint**. Connect the GitHub repository and select it.
3. Review the service settings from `render.yaml`, then apply the Blueprint. Render builds and starts the game.
4. When the service is ready, open its `onrender.com` URL. Create a room, then send that same URL and the room code to your friend. Your friend opens the link on a different network and joins with the code.

The free service can go to sleep after a period without visitors, so the first visit after sleep may take about a minute. Game rooms and scores live in server memory: a restart, redeploy, or free-service sleep can clear active games. This setup is for casual play and testing, not a production service; it does not add accounts, persistent scores, or a database. Keep only one server instance for this in-memory version.

## Scope and limitations

- Rooms exist only in the running Python process; restarting the server clears them.
- A room supports two connected players. If a player leaves or disconnects, the remaining player can wait for a replacement and the board resets.
- The best-of-three scoreboard resets when a player leaves; round wins and draws remain in memory only while that room is running.
- This is a hobby prototype. It does not provide persistent accounts or scores, or production security. Public play requires deploying the server to a suitable host; the Render setup above provides a small test deployment.
- The page loads Socket.IO client 4.8.1 from a CDN; the browser needs network access for that script. The game server itself runs locally.
