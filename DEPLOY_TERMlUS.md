# Deploy with GitHub + Termius

This project is standalone and should use its own folder/service. Do not overwrite the existing Sylvo/Gurga installation.

## 1. Push from your computer to a NEW private GitHub repository
Create a private repository named `edge-intelligence` (or your chosen name), then:
```bash
git init
git add .
git commit -m "Initial Edge Intelligence MVP"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/edge-intelligence.git
git push -u origin main
```
Do not commit `.env`, database files, API keys or credentials.

## 2. SSH into your VPS in Termius
Use your VPS login. Commands below assume Ubuntu/Debian and a user with sudo access.

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
sudo mkdir -p /opt/edge-intelligence
sudo chown "$USER":"$USER" /opt/edge-intelligence
git clone https://github.com/YOUR_USERNAME/edge-intelligence.git /opt/edge-intelligence
cd /opt/edge-intelligence
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
mkdir -p data
```

If GitHub asks for credentials, use a GitHub token or SSH key; never paste tokens into this repository.

## 3. Run a smoke test
```bash
cd /opt/edge-intelligence
.venv/bin/python -m unittest -v
.venv/bin/python -c "from app import app; c=app.test_client(); print(c.get('/health').status_code, c.get('/health').json)"
```
Do not continue if tests fail.

## 4. Create a systemd service
```bash
sudo tee /etc/systemd/system/edge-intelligence.service >/dev/null <<'EOF'
[Unit]
Description=Edge Intelligence mobile trading research app
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/edge-intelligence
Environment=PORT=5060
Environment=EDGE_DB_PATH=/var/lib/edge-intelligence/edge.db
ExecStartPre=/usr/bin/mkdir -p /var/lib/edge-intelligence
ExecStart=/opt/edge-intelligence/.venv/bin/gunicorn --workers 2 --threads 4 --bind 127.0.0.1:5060 --timeout 60 app:app
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=/var/lib/edge-intelligence

[Install]
WantedBy=multi-user.target
EOF
sudo mkdir -p /var/lib/edge-intelligence
sudo chown -R www-data:www-data /var/lib/edge-intelligence
sudo chown -R "$USER":"$USER" /opt/edge-intelligence
sudo systemctl daemon-reload
sudo systemctl enable --now edge-intelligence
sudo systemctl status edge-intelligence --no-pager
curl -sS http://127.0.0.1:5060/health
```

## 5. Nginx
Use a new hostname/subdomain if possible. Example server block (replace `edge.example.com`):
```nginx
server {
    listen 80;
    server_name edge.example.com;
    location / {
        proxy_pass http://127.0.0.1:5060;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }
}
```
Then test and reload:
```bash
sudo nginx -t && sudo systemctl reload nginx
```
Enable TLS after DNS points to the server, using your existing Certbot workflow. Do not expose port 5060 directly to the public internet.

## 6. Updates after pushing to GitHub
```bash
cd /opt/edge-intelligence
git pull --ff-only origin main
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest -v
sudo systemctl restart edge-intelligence
curl -sS http://127.0.0.1:5060/health
```

## Troubleshooting
```bash
sudo journalctl -u edge-intelligence -n 100 --no-pager
sudo systemctl status edge-intelligence --no-pager
curl -i http://127.0.0.1:5060/health
```

Do not restart a production service after failed tests. Back up `/var/lib/edge-intelligence/edge.db` before schema changes.
