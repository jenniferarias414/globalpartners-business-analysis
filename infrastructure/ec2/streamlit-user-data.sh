#!/usr/bin/env bash
set -euo pipefail

exec > >(tee /var/log/globalpartners-streamlit-bootstrap.log | logger -t globalpartners-bootstrap -s 2>/dev/console) 2>&1
trap 'touch /var/tmp/globalpartners-streamlit-bootstrap-failed' ERR

REPOSITORY_URL="https://github.com/jenniferarias414/globalpartners-business-analysis.git"
DEPLOY_REF="main"
APPLICATION_DIR="/opt/globalpartners-business-analysis"
VIRTUAL_ENV="$APPLICATION_DIR/.venv"

dnf update -y
dnf install -y git python3 python3-pip

if [[ -d "$APPLICATION_DIR/.git" ]]; then
    git -C "$APPLICATION_DIR" fetch --all --prune
else
    git clone "$REPOSITORY_URL" "$APPLICATION_DIR"
fi

git -C "$APPLICATION_DIR" checkout --detach "$DEPLOY_REF"

python3 -m venv "$VIRTUAL_ENV"
"$VIRTUAL_ENV/bin/python" -m pip install --upgrade pip
"$VIRTUAL_ENV/bin/python" -m pip install \
    -r "$APPLICATION_DIR/streamlit/requirements-streamlit.txt"

chown -R ec2-user:ec2-user "$APPLICATION_DIR"

cat >/etc/systemd/system/globalpartners-streamlit.service <<'UNIT'
[Unit]
Description=GlobalPartners Streamlit Dashboard
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ec2-user
Group=ec2-user
WorkingDirectory=/opt/globalpartners-business-analysis
Environment=HOME=/home/ec2-user
Environment=AWS_REGION=us-east-2
Environment=AWS_DEFAULT_REGION=us-east-2
Environment=GP_ATHENA_WORKGROUP=globalpartners-analysis
Environment=GP_GLUE_DATABASE=globalpartners_gold
ExecStart=/opt/globalpartners-business-analysis/.venv/bin/python -m streamlit run /opt/globalpartners-business-analysis/streamlit/app.py --server.address=0.0.0.0 --server.port=8501 --server.headless=true --browser.gatherUsageStats=false
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now globalpartners-streamlit.service

touch /var/tmp/globalpartners-streamlit-bootstrap-complete
rm -f /var/tmp/globalpartners-streamlit-bootstrap-failed
