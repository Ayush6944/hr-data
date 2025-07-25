import time
import subprocess
from datetime import datetime, timedelta
import pytz
import threading
from flask import Flask, send_file, request, redirect, url_for, session, render_template_string
import os
import requests
from typing import Optional

# ===================== CONFIGURATION =====================
SCHEDULE_HOUR = 12  # 10 AM (used after first run)
SCHEDULE_MINUTE = 25 # 20 minutes (used after first run)
IST = pytz.timezone('Asia/Kolkata')
LOG_FILE = 'scheduler_audit.log'
LOGIN_LOG_FILE = 'login_audit.log'
SECRET_KEY = 'supersecretkey'  # Change this in production
USERNAME = 'admin'
PASSWORD = 'ayush'
# ========================================================

app = Flask(__name__)
app.secret_key = SECRET_KEY

last_run_info: dict[str, Optional[str]] = {'start': None, 'end': None, 'error': None}

def log_login_event(username, success):
    with open(LOGIN_LOG_FILE, 'a', encoding='utf-8') as f:
        status = 'SUCCESS' if success else 'FAIL'
        f.write(f"{datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')} - {username} - {status}\n")

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == USERNAME and password == PASSWORD:
            session['logged_in'] = True
            session['username'] = username
            log_login_event(username, True)
            # Show Kali OS-style animation before redirect
            return render_template_string('''
            <html>
            <head>
                <title>Logging In...</title>
                <style>
                    body { background: #181c20; color: #39ff14; margin: 0; height: 100vh; overflow: hidden; }
                    .terminal {
                        font-family: 'Fira Mono', 'Consolas', monospace;
                        background: #181c20;
                        color: #39ff14;
                        width: 100vw;
                        height: 100vh;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        flex-direction: column;
                        font-size: 1.3em;
                    }
                    .blink {
                        animation: blink 1s steps(2, start) infinite;
                    }
                    @keyframes blink {
                        to { visibility: hidden; }
                    }
                </style>
                <script>
                    let lines = [
                        'Welcome, {{ username }}',
                        'Initializing secure session...',
                        'Loading dashboard modules...',
                        'Access granted. Redirecting...'
                    ];
                    let idx = 0;
                    function typeLine() {
                        if (idx < lines.length) {
                            let term = document.getElementById('term');
                            let p = document.createElement('div');
                            p.textContent = lines[idx];
                            term.appendChild(p);
                            idx++;
                            setTimeout(typeLine, 900);
                        } else {
                            setTimeout(function() { window.location = "/"; }, 1200);
                        }
                    }
                    window.onload = typeLine;
                </script>
            </head>
            <body>
                <div class="terminal" id="term">
                    <span class="blink">root@hr-emailer:~#</span>
                </div>
            </body>
            </html>
            ''', username=username)
        else:
            log_login_event(username or '', False)
            error = 'Invalid username or password.'
    return render_template_string('''
    <html>
    <head>
        <title>Login - Email Campaign Scheduler</title>
        <style>
            body { font-family: Arial, sans-serif; background: #181c20; }
            .login-container {
                max-width: 350px; margin: 6em auto; background: #23272e;
                border-radius: 10px; box-shadow: 0 4px 24px rgba(44,62,80,0.18);
                padding: 2.5em 2.5em; text-align: center;
            }
            h2 { color: #39ff14; letter-spacing: 1px; }
            input[type=text], input[type=password] {
                width: 90%; padding: 0.7em; margin: 1em 0 1.5em 0; border: 1px solid #444; border-radius: 4px; background: #181c20; color: #39ff14;
            }
            button { background: linear-gradient(90deg, #39ff14 0%, #00c3ff 100%); color: #181c20; border: none; padding: 0.7em 2em; border-radius: 4px; font-size: 1em; cursor: pointer; font-weight: bold; }
            button:hover { background: #39ff14; color: #23272e; }
            .error { color: #e74c3c; margin-bottom: 1em; }
        </style>
    </head>
    <body>
        <div class="login-container">
            <h2>Login</h2>
            {% if error %}<div class="error">{{ error }}</div>{% endif %}
            <form method="post">
                <input type="text" name="username" placeholder="Username" required><br>
                <input type="password" name="password" placeholder="Password" required><br>
                <button type="submit">Login</button>
            </form>
        </div>
    </body>
    </html>
    ''', error=error)

@app.route('/logout', methods=['GET', 'POST'])
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/logged_out')
def logged_out():
    return render_template_string('''
    <html>
    <head>
        <title>Logged Out</title>
        <style>
            body { font-family: Arial, sans-serif; background: #f7f7f7; }
            .logout-container {
                max-width: 350px; margin: 6em auto; background: #fff;
                border-radius: 8px; box-shadow: 0 2px 8px rgba(44,62,80,0.08);
                padding: 2em 2.5em; text-align: center;
            }
            h2 { color: #2c3e50; }
            button { background: #2c3e50; color: #fff; border: none; padding: 0.7em 2em; border-radius: 4px; font-size: 1em; cursor: pointer; margin-top: 2em; }
            button:hover { background: #e74c3c; }
        </style>
        <script>
            function closeTab() {
                window.open('', '_self', '');
                window.close();
            }
        </script>
    </head>
    <body>
        <div class="logout-container">
            <h2>You have been logged out.</h2>
            <p>For your security, please close this tab.</p>
            <button onclick="closeTab()">Close Tab</button>
        </div>
    </body>
    </html>
    ''')

# Update navigation and color palette for home, dashboard, and email_status
# --- HOME PAGE ---
@app.route('/')
@login_required
def home():
    return render_template_string('''
    <html>
    <head>
        <title>Email Campaign Scheduler</title>
        <link href="https://fonts.googleapis.com/css?family=Fira+Mono:400,700&display=swap" rel="stylesheet">
        <style>
            body {
                font-family: 'Fira Mono', 'Consolas', monospace;
                background: linear-gradient(135deg, #f8fafc 0%, #e9ecef 100%);
                margin: 0;
                min-height: 100vh;
                color: #222;
                transition: background 0.3s, color 0.3s;
            }
            body.dark-mode {
                background: linear-gradient(135deg, #181c20 0%, #23272e 100%);
                color: #fff;
            }
            .navbar {
                background: #f5f6fa;
                padding: 1.2em 2em;
                display: flex;
                align-items: center;
                box-shadow: 0 2px 8px rgba(44,62,80,0.08);
                transition: background 0.3s;
            }
            .navbar.dark-mode {
                background: #181c20;
            }
            .navbar a {
                color: #0071e3;
                text-decoration: none;
                margin-right: 2em;
                font-weight: bold;
                font-size: 1.1em;
                transition: color 0.2s;
                letter-spacing: 1px;
            }
            .navbar a:hover {
                color: #222;
            }
            .navbar.dark-mode a {
                color: #e0c36b;
            }
            .navbar.dark-mode a:hover {
                color: #fff;
            }
            .logout-btn {
                float: right; background: #e74c3c; color: #fff; border: none; padding: 0.5em 1.2em; border-radius: 4px; cursor: pointer; margin-left: auto; font-weight: bold;
            }
            .logout-btn:hover { background: #c0392b; }
            .theme-switch {
                margin-left: 2em;
                display: flex;
                align-items: center;
            }
            .switch {
                position: relative;
                display: inline-block;
                width: 48px;
                height: 24px;
            }
            .switch input { display: none; }
            .slider {
                position: absolute;
                cursor: pointer;
                top: 0; left: 0; right: 0; bottom: 0;
                background: #ccc;
                transition: .4s;
                border-radius: 24px;
            }
            .slider:before {
                position: absolute;
                content: "";
                height: 18px;
                width: 18px;
                left: 3px;
                bottom: 3px;
                background: #fff;
                transition: .4s;
                border-radius: 50%;
            }
            input:checked + .slider {
                background: #0071e3;
            }
            input:checked + .slider:before {
                transform: translateX(24px);
            }
            .container {
                max-width: 700px;
                margin: 4em auto;
                background: #fff;
                border-radius: 12px;
                box-shadow: 0 4px 24px rgba(44,62,80,0.08);
                padding: 2.5em 2.5em;
                text-align: center;
                color: #222;
            }
            .container.dark-mode { background: #23272e; color: #fff; }
            h1, h2, h4 { color: #0071e3; }
            h1.dark-mode, h2.dark-mode, h4.dark-mode { color: #e0c36b; }
            .download-link {
                color: #0071e3; text-decoration: underline; font-weight: bold;
            }
            .download-link:hover { color: #222; }
            hr { border: 0; border-top: 1px solid #e0e0e0; margin: 2em 0; }
            .footer { margin-top: 2em; color: #888; font-size: 0.95em; }
        </style>
    </head>
    <body>
        <div class="navbar" id="navbar">
            <a href="/">Home</a>
            <a href="/status">Status Log</a>
            <a href="/dashboard">Dashboard</a>
            <a href="/email_status">Email Status</a>
            <a href="/download_log">Download Log</a>
            <div class="theme-switch">
                <label class="switch">
                    <input type="checkbox" id="theme-toggle">
                    <span class="slider"></span>
                </label>
                <span style="margin-left:0.7em;font-size:1em;">Dark Mode</span>
            </div>
            <form action="/logout" method="get" style="margin-left:auto;display:inline;">
                <button class="logout-btn" type="submit">Logout</button>
            </form>
        </div>
        <div class="container" id="main-container">
            <h1 id="main-title">Welcome to the Email Campaign Scheduler</h1>
            <p>Use the navigation bar above to view campaign status, logs, and analytics.</p>
            <p style="color:#888; font-size:0.95em;">Server is running and ready to manage your automated email campaigns.</p>
            <hr>
            <p><b>Download your full email send log as a CSV file:</b><br>
            <a class="download-link" href="/download_log">Download send_log.csv</a></p>
            <div class="footer">
                <h4>Created By - Ayush Srivastava | <a href="https://portfolio-ayush6944s-projects.vercel.app/" style="color:#0071e3;">Portfolio</a></h4>
            </div>
        </div>
        <script>
        // Universal dark mode switcher
        const themeToggle = document.getElementById('theme-toggle');
        const body = document.body;
        const navbar = document.getElementById('navbar');
        const mainContainer = document.getElementById('main-container');
        const mainTitle = document.getElementById('main-title');
        function setDarkMode(on) {
            if (on) {
                body.classList.add('dark-mode');
                navbar.classList.add('dark-mode');
                mainContainer.classList.add('dark-mode');
                mainTitle.classList.add('dark-mode');
            } else {
                body.classList.remove('dark-mode');
                navbar.classList.remove('dark-mode');
                mainContainer.classList.remove('dark-mode');
                mainTitle.classList.remove('dark-mode');
            }
        }
        themeToggle.addEventListener('change', function() {
            setDarkMode(this.checked);
            localStorage.setItem('darkMode', this.checked ? '1' : '0');
        });
        if (localStorage.getItem('darkMode') === '1') {
            themeToggle.checked = true;
            setDarkMode(true);
        }
        </script>
    </body>
    </html>
    ''')

@app.route('/status')
@login_required
def status():
    log_lines = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            log_lines = f.readlines()[-10:]
    html = '''
    <html>
    <head>
        <title>Status Log - Email Campaign Scheduler</title>
        <link href="https://fonts.googleapis.com/css?family=Fira+Mono:400,700&display=swap" rel="stylesheet">
        <style>
            body {
                font-family: 'Fira Mono', 'Consolas', monospace;
                background: linear-gradient(135deg, #181c20 0%, #23272e 100%);
                margin: 0;
                min-height: 100vh;
            }
            .navbar {
                background: #181c20;
                padding: 1.2em 2em;
                display: flex;
                align-items: center;
                box-shadow: 0 2px 8px rgba(44,62,80,0.18);
            }
            .navbar a {
                color: #39ff14;
                text-decoration: none;
                margin-right: 2em;
                font-weight: bold;
                font-size: 1.1em;
                transition: color 0.2s;
                letter-spacing: 1px;
            }
            .navbar a:hover {
                color: #00c3ff;
            }
            .container {
                max-width: 700px;
                margin: 4em auto;
                background: #23272e;
                border-radius: 12px;
                box-shadow: 0 4px 24px rgba(44,62,80,0.18);
                padding: 2.5em 2.5em;
                color: #fff;
            }
            h1 {
                color: #39ff14;
                font-size: 2em;
                margin-bottom: 1em;
            }
            .log-card {
                background: #181c20;
                border-radius: 8px;
                box-shadow: 0 2px 8px rgba(44,62,80,0.18);
                padding: 1.5em 2em;
                margin: 2em 0;
                font-size: 1.1em;
                color: #00c3ff;
                min-height: 180px;
                white-space: pre-line;
            }
            .empty-log { color: #e74c3c; }
        </style>
    </head>
    <body>
        <div class="navbar">
            <a href="/">Home</a>
            <a href="/status">Status Log</a>
            <a href="/dashboard">Dashboard</a>
            <a href="/download_log">Download Log</a>
            <form action="/logout" method="get" style="margin-left:auto;display:inline;">
                <button class="logout-btn" type="submit">Logout</button>
            </form>
        </div>
        <div class="container">
            <h1>Status Log</h1>
            <div class="log-card">'''
    if log_lines:
        html += ''.join(line + '<br>' for line in log_lines)
    else:
        html += '<span class="empty-log">No audit log found.</span>'
    html += '''</div>
        </div>
    </body>
    </html>
    '''
    return html

# --- DASHBOARD PAGE ---
@app.route('/dashboard')
@login_required
def dashboard():
    import sqlite3
    from datetime import datetime, timedelta
    db_path = os.path.join(os.path.dirname(__file__), 'data/companies.db')
    total_sent = 0
    total_pending = 0
    last_10_days = []
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM companies WHERE sent_timestamp IS NOT NULL")
            total_sent = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM companies WHERE sent_timestamp IS NULL")
            total_pending = cursor.fetchone()[0]
            today = datetime.now().date()
            for i in range(9, -1, -1):
                day = today - timedelta(days=i)
                cursor.execute("SELECT COUNT(*) FROM companies WHERE date(sent_timestamp) = ?", (day.isoformat(),))
                count = cursor.fetchone()[0]
                last_10_days.append({'date': day.strftime('%Y-%m-%d'), 'count': count})
    except Exception as e:
        return f"<h2>Error loading dashboard: {e}</h2>"
    # Prepare chart data and table rows to avoid nested expressions in f-strings
    import json as _json
    chart_labels = _json.dumps([d['date'] for d in last_10_days])
    chart_data = _json.dumps([d['count'] for d in last_10_days])
    table_rows = ''.join([f'<tr><td>{row["date"]}</td><td>{row["count"]}</td></tr>' for row in last_10_days])
    total_sent_js = total_sent
    total_pending_js = total_pending
    html = f"""
    <html>
    <head><title>Email Campaign Dashboard</title>
    <link href='https://fonts.googleapis.com/css?family=Fira+Mono:400,700&display=swap' rel='stylesheet'>
    <script src=\"https://cdn.jsdelivr.net/npm/chart.js\"></script>
    <style>
        body {{
            font-family: 'Fira Mono', 'Consolas', monospace;
            background: linear-gradient(135deg, #f8fafc 0%, #e9ecef 100%);
            margin: 0;
            min-height: 100vh;
            color: #222;
            transition: background 0.3s, color 0.3s;
        }}
        body.dark-mode {{
            background: linear-gradient(135deg, #181c20 0%, #23272e 100%);
            color: #fff;
        }}
        .navbar {{
            background: #f5f6fa;
            padding: 1.2em 2em;
            display: flex;
            align-items: center;
            box-shadow: 0 2px 8px rgba(44,62,80,0.08);
            transition: background 0.3s;
        }}
        .navbar.dark-mode {{
            background: #181c20;
        }}
        .navbar a {{
            color: #0071e3;
            text-decoration: none;
            margin-right: 2em;
            font-weight: bold;
            font-size: 1.1em;
            transition: color 0.2s;
            letter-spacing: 1px;
        }}
        .navbar a:hover {{
            color: #222;
        }}
        .navbar.dark-mode a {{
            color: #e0c36b;
        }}
        .navbar.dark-mode a:hover {{
            color: #fff;
        }}
        .logout-btn {{
            float: right; background: #e74c3c; color: #fff; border: none; padding: 0.5em 1.2em; border-radius: 4px; cursor: pointer; margin-left: auto; font-weight: bold;
        }}
        .logout-btn:hover {{ background: #c0392b; }}
        .theme-switch {{
            margin-left: 2em;
            display: flex;
            align-items: center;
        }}
        .switch {{
            position: relative;
            display: inline-block;
            width: 48px;
            height: 24px;
        }}
        .switch input {{ display: none; }}
        .slider {{
            position: absolute;
            cursor: pointer;
            top: 0; left: 0; right: 0; bottom: 0;
            background: #ccc;
            transition: .4s;
            border-radius: 24px;
        }}
        .slider:before {{
            position: absolute;
            content: "";
            height: 18px;
            width: 18px;
            left: 3px;
            bottom: 3px;
            background: #fff;
            transition: .4s;
            border-radius: 50%;
        }}
        input:checked + .slider {{
            background: #0071e3;
        }}
        input:checked + .slider:before {{
            transform: translateX(24px);
        }}
        .dashboard-container {{
            max-width: 700px;
            margin: 4em auto;
            background: #fff;
            border-radius: 18px;
            box-shadow: 0 8px 32px rgba(44,62,80,0.08);
            padding: 2.5em 2.5em;
            color: #222;
            transition: background 0.3s, color 0.3s;
        }}
        .dashboard-container.dark-mode {{
            background: #23272e;
            color: #fff;
        }}
        h1 {{ color: #0071e3; font-size: 2.2em; margin-bottom: 1.2em; letter-spacing: 2px; }}
        h1.dark-mode {{ color: #e0c36b; }}
        .stats {{ display: flex; justify-content: space-between; margin-bottom: 2.5em; gap: 2em; }}
        .stat-card {{ background: #f5f6fa; border-radius: 12px; padding: 2em 2.5em; box-shadow: 0 2px 12px rgba(44,62,80,0.08); text-align: center; flex: 1; transition: background 0.3s, color 0.3s; }}
        .stat-card.dark-mode {{ background: #181c20; color: #fff; }}
        .stat-label {{ color: #888; font-size: 1.1em; margin-bottom: 0.7em; letter-spacing: 1px; }}
        .stat-label.dark-mode {{ color: #bfa14a; }}
        .stat-value {{ color: #0071e3; font-size: 2.5em; font-weight: bold; letter-spacing: 1px; }}
        .stat-value.dark-mode {{ color: #e0c36b; }}
        .charts-row {{ display: flex; gap: 2em; margin-top: 2em; margin-bottom: 2em; flex-wrap: wrap; }}
        .chart-card {{ background: #f5f6fa; border-radius: 12px; box-shadow: 0 2px 12px rgba(44,62,80,0.08); padding: 1.5em 1em; flex: 1; min-width: 300px; transition: background 0.3s, color 0.3s; }}
        .chart-card.dark-mode {{ background: #181c20; color: #fff; }}
        .section-title {{ color: #888; font-size: 1.3em; margin-top: 2.5em; margin-bottom: 1em; letter-spacing: 1px; text-align: left; }}
        .section-title.dark-mode {{ color: #bfa14a; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 2.5em; background: #f5f6fa; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 8px rgba(44,62,80,0.05); }}
        table.dark-mode {{ background: #181c20; color: #fff; }}
        th, td {{ padding: 1em; text-align: center; }}
        th {{ background: #e9ecef; color: #0071e3; font-size: 1.1em; letter-spacing: 1px; }}
        th.dark-mode {{ background: #23272e; color: #e0c36b; }}
        tr:nth-child(even) {{ background: #f5f6fa; }}
        tr:nth-child(odd) {{ background: #fff; }}
        tr.dark-mode:nth-child(even) {{ background: #23272e; }}
        tr.dark-mode:nth-child(odd) {{ background: #181c20; }}
        button {{ background: #e74c3c; color: #fff; border: none; padding: 0.7em 2em; border-radius: 4px; font-size: 1em; cursor: pointer; margin-top: 2em; font-weight: bold; }}
        button:hover {{ background: #c0392b; }}
    </style>
    </head>
    <body>
        <div class='navbar' id='navbar'>
            <a href=\"/\">Home</a>
            <a href=\"/status\">Status Log</a>
            <a href=\"/dashboard\">Dashboard</a>
            <a href=\"/email_status\">Email Status</a>
            <a href=\"/download_log\">Download Log</a>
            <div class="theme-switch">
                <label class="switch">
                    <input type="checkbox" id="theme-toggle">
                    <span class="slider"></span>
                </label>
                <span style="margin-left:0.7em;font-size:1em;">Dark Mode</span>
            </div>
            <form action="/logout" method="get" style="margin-left:auto;display:inline;">
                <button class="logout-btn" type="submit">Logout</button>
            </form>
        </div>
        <div class='dashboard-container' id='dashboard-container'>
            <h1 id='dashboard-title'>Email Campaign Dashboard</h1>
            <div class='stats'>
                <div class='stat-card' id='stat-card-sent'>
                    <div class='stat-label' id='stat-label-sent'>Total Sent Emails</div>
                    <div class='stat-value' id='stat-value-sent'>{total_sent}</div>
                </div>
                <div class='stat-card' id='stat-card-pending'>
                    <div class='stat-label' id='stat-label-pending'>Total Pending Emails</div>
                    <div class='stat-value' id='stat-value-pending'>{total_pending}</div>
                </div>
            </div>
            <div class='charts-row'>
                <div class='chart-card' id='chart-card-line'>
                    <canvas id="lineChart" width="350" height="220"></canvas>
                </div>
                <div class='chart-card' id='chart-card-doughnut'>
                    <canvas id="doughnutChart" width="220" height="220"></canvas>
                </div>
            </div>
            <div class='section-title' id='section-title-table'>Last 10 Days Email Sent</div>
            <table id='progress-table'>
                <tr><th>Date</th><th>Emails Sent</th></tr>
                {table_rows}
            </table>
            <form action="/stop_campaign" method="post">
                <button type="submit">Stop Campaign</button>
            </form>
        </div>
        <script>
        // Chart.js line chart for last 10 days
        const ctxLine = document.getElementById('lineChart').getContext('2d');
        const lineChart = new Chart(ctxLine, {{
            type: 'line',
            data: {{
                labels: {chart_labels},
                datasets: [{{
                    label: 'Emails Sent',
                    data: {chart_data},
                    borderColor: '#0071e3',
                    backgroundColor: 'rgba(0,113,227,0.08)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 4,
                    pointBackgroundColor: '#0071e3',
                }}]
            }},
            options: {{
                plugins: {{ legend: {{ display: false }} }},
                scales: {{
                    x: {{ grid: {{ display: false }} }},
                    y: {{ beginAtZero: true, grid: {{ color: '#e0e0e0' }} }}
                }}
            }}
        }});
        // Chart.js doughnut chart for sent vs pending
        const ctxDoughnut = document.getElementById('doughnutChart').getContext('2d');
        const doughnutChart = new Chart(ctxDoughnut, {{
            type: 'doughnut',
            data: {{
                labels: ['Sent', 'Pending'],
                datasets: [{{
                    data: [{total_sent_js}, {total_pending_js}],
                    backgroundColor: ['#0071e3', '#e0e0e0'],
                    borderWidth: 0
                }}]
            }},
            options: {{
                plugins: {{ legend: {{ display: true, position: 'bottom' }} }},
                cutout: '70%',
            }}
        }});
        // Theme switcher
        const themeToggle = document.getElementById('theme-toggle');
        const body = document.body;
        const navbar = document.getElementById('navbar');
        const dashboardContainer = document.getElementById('dashboard-container');
        const dashboardTitle = document.getElementById('dashboard-title');
        const statCardSent = document.getElementById('stat-card-sent');
        const statCardPending = document.getElementById('stat-card-pending');
        const statLabelSent = document.getElementById('stat-label-sent');
        const statLabelPending = document.getElementById('stat-label-pending');
        const statValueSent = document.getElementById('stat-value-sent');
        const statValuePending = document.getElementById('stat-value-pending');
        const chartCardLine = document.getElementById('chart-card-line');
        const chartCardDoughnut = document.getElementById('chart-card-doughnut');
        const sectionTitleTable = document.getElementById('section-title-table');
        const progressTable = document.getElementById('progress-table');
        function setDarkMode(on) {{
            if (on) {{
                body.classList.add('dark-mode');
                navbar.classList.add('dark-mode');
                dashboardContainer.classList.add('dark-mode');
                dashboardTitle.classList.add('dark-mode');
                statCardSent.classList.add('dark-mode');
                statCardPending.classList.add('dark-mode');
                statLabelSent.classList.add('dark-mode');
                statLabelPending.classList.add('dark-mode');
                statValueSent.classList.add('dark-mode');
                statValuePending.classList.add('dark-mode');
                chartCardLine.classList.add('dark-mode');
                chartCardDoughnut.classList.add('dark-mode');
                sectionTitleTable.classList.add('dark-mode');
                progressTable.classList.add('dark-mode');
                for (const row of progressTable.rows) row.classList.add('dark-mode');
            }} else {{
                body.classList.remove('dark-mode');
                navbar.classList.remove('dark-mode');
                dashboardContainer.classList.remove('dark-mode');
                dashboardTitle.classList.remove('dark-mode');
                statCardSent.classList.remove('dark-mode');
                statCardPending.classList.remove('dark-mode');
                statLabelSent.classList.remove('dark-mode');
                statLabelPending.classList.remove('dark-mode');
                statValueSent.classList.remove('dark-mode');
                statValuePending.classList.remove('dark-mode');
                chartCardLine.classList.remove('dark-mode');
                chartCardDoughnut.classList.remove('dark-mode');
                sectionTitleTable.classList.remove('dark-mode');
                progressTable.classList.remove('dark-mode');
                for (const row of progressTable.rows) row.classList.remove('dark-mode');
            }}
        }}
        themeToggle.addEventListener('change', function() {{
            setDarkMode(this.checked);
            localStorage.setItem('darkMode', this.checked ? '1' : '0');
        }});
        // On load, set theme from localStorage
        if (localStorage.getItem('darkMode') === '1') {{
            themeToggle.checked = true;
            setDarkMode(true);
        }}
        </script>
    </body>
    </html>
    """
    return html

# --- EMAIL STATUS PAGE ---
@app.route('/email_status')
@login_required
def email_status():
    import csv
    import json
    from collections import defaultdict
    accounts_path = os.path.join(os.path.dirname(__file__), 'src/email_accounts.json')
    with open(accounts_path, 'r') as f:
        accounts_json = json.load(f)
        sender_accounts = accounts_json['email_accounts']
    send_counts = defaultdict(int)
    today = datetime.now().date().isoformat()
    send_log_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../data/send_log.csv'))
    if os.path.exists(send_log_path):
        with open(send_log_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['date_sent'][:10] == today:
                    send_counts[row['sender_email']] += 1
    table_rows = ''.join([f'<tr><td>{acc["sender_email"]}</td><td>Session Only</td><td>{send_counts.get(acc["sender_email"], 0)}</td></tr>' for acc in sender_accounts])
    html = f"""
    <html>
    <head><title>Email Account Status</title>
    <link href='https://fonts.googleapis.com/css?family=Fira+Mono:400,700&display=swap' rel='stylesheet'>
    <style>
        body {{
            font-family: 'Fira Mono', 'Consolas', monospace;
            background: linear-gradient(135deg, #f8fafc 0%, #e9ecef 100%);
            margin: 0;
            min-height: 100vh;
            color: #222;
            transition: background 0.3s, color 0.3s;
        }}
        body.dark-mode {{
            background: linear-gradient(135deg, #181c20 0%, #23272e 100%);
            color: #fff;
        }}
        .navbar {{
            background: #f5f6fa;
            padding: 1.2em 2em;
            display: flex;
            align-items: center;
            box-shadow: 0 2px 8px rgba(44,62,80,0.08);
            transition: background 0.3s;
        }}
        .navbar.dark-mode {{
            background: #181c20;
        }}
        .navbar a {{
            color: #0071e3;
            text-decoration: none;
            margin-right: 2em;
            font-weight: bold;
            font-size: 1.1em;
            transition: color 0.2s;
            letter-spacing: 1px;
        }}
        .navbar a:hover {{
            color: #222;
        }}
        .navbar.dark-mode a {{
            color: #e0c36b;
        }}
        .navbar.dark-mode a:hover {{
            color: #fff;
        }}
        .logout-btn {{
            float: right; background: #e74c3c; color: #fff; border: none; padding: 0.5em 1.2em; border-radius: 4px; cursor: pointer; margin-left: auto; font-weight: bold;
        }}
        .logout-btn:hover {{ background: #c0392b; }}
        .theme-switch {{
            margin-left: 2em;
            display: flex;
            align-items: center;
        }}
        .switch {{
            position: relative;
            display: inline-block;
            width: 48px;
            height: 24px;
        }}
        .switch input {{ display: none; }}
        .slider {{
            position: absolute;
            cursor: pointer;
            top: 0; left: 0; right: 0; bottom: 0;
            background: #ccc;
            transition: .4s;
            border-radius: 24px;
        }}
        .slider:before {{
            position: absolute;
            content: "";
            height: 18px;
            width: 18px;
            left: 3px;
            bottom: 3px;
            background: #fff;
            transition: .4s;
            border-radius: 50%;
        }}
            input:checked + .slider {{
            background: #0071e3;
        }}
        input:checked + .slider:before {{
            transform: translateX(24px);
        }}
        .status-container {{
            max-width: 700px;
            margin: 4em auto;
            background: #fff;
            border-radius: 18px;
            box-shadow: 0 8px 32px rgba(44,62,80,0.08);
            padding: 2.5em 2.5em;
            color: #222;
            transition: background 0.3s, color 0.3s;
        }}
        .status-container.dark-mode {{ background: #23272e; color: #fff; }}
        h1 {{ color: #0071e3; font-size: 2.2em; margin-bottom: 1.2em; letter-spacing: 2px; }}
        h1.dark-mode {{ color: #e0c36b; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 2.5em; background: #f5f6fa; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 8px rgba(44,62,80,0.05); }}
        table.dark-mode {{ background: #181c20; color: #fff; }}
        th, td {{ padding: 1em; text-align: center; }}
        th {{ background: #e9ecef; color: #0071e3; font-size: 1.1em; letter-spacing: 1px; }}
        th.dark-mode {{ background: #23272e; color: #e0c36b; }}
                tr:nth-child(even) {{ background: #f5f6fa; }}
        tr:nth-child(odd) {{ background: #fff; }}
        tr.dark-mode:nth-child(even) {{ background: #23272e; }}
        tr.dark-mode:nth-child(odd) {{ background: #181c20; }}
    </style>
    </head>
    <body>
        <div class='navbar' id='navbar'>
            <a href="/">Home</a>
            <a href="/status">Status Log</a>
            <a href="/dashboard">Dashboard</a>
            <a href="/email_status">Email Status</a>
            <a href="/download_log">Download Log</a>
            <div class="theme-switch">
                <label class="switch">
                    <input type="checkbox" id="theme-toggle">
                    <span class="slider"></span>
                </label>
                <span style="margin-left:0.7em;font-size:1em;">Dark Mode</span>
            </div>
            <form action="/logout" method="get" style="margin-left:auto;display:inline;">
                <button class="logout-btn" type="submit">Logout</button>
            </form>
        </div>
        <div class='status-container' id='status-container'>
            <h1 id='status-title'>Email Account Status</h1>
            <table id='status-table'>
                <tr><th>Sender Email</th><th>Exhausted (Today)</th><th>Emails Sent Today</th></tr>
                {table_rows}
            </table>
        </div>
        <script>
        // Universal dark mode switcher
        const themeToggle = document.getElementById('theme-toggle');
        const body = document.body;
        const navbar = document.getElementById('navbar');
        const statusContainer = document.getElementById('status-container');
        const statusTitle = document.getElementById('status-title');
        const statusTable = document.getElementById('status-table');
        function setDarkMode(on) {{
            if (on) {{
                body.classList.add('dark-mode');
                navbar.classList.add('dark-mode');
                statusContainer.classList.add('dark-mode');
                statusTitle.classList.add('dark-mode');
                statusTable.classList.add('dark-mode');
                for (const row of statusTable.rows) row.classList.add('dark-mode');
            }} else {{
                body.classList.remove('dark-mode');
                navbar.classList.remove('dark-mode');
                statusContainer.classList.remove('dark-mode');
                statusTitle.classList.remove('dark-mode');
                statusTable.classList.remove('dark-mode');
                for (const row of statusTable.rows) row.classList.remove('dark-mode');
            }}
        }}
        themeToggle.addEventListener('change', function() {{
            setDarkMode(this.checked);
            localStorage.setItem('darkMode', this.checked ? '1' : '0');
        }});
        if (localStorage.getItem('darkMode') === '1') {{
            themeToggle.checked = true;
            setDarkMode(true);
        }}
        </script>
    </body>
    </html>
    """
    return html

@app.route('/download_log')
@login_required
def download_log():
    import os
    log_path = os.path.join(os.path.dirname(__file__), 'data/send_log.csv')
    if not os.path.exists(log_path):
        return '<h2>send_log.csv not found.</h2>', 404
    return send_file(log_path, as_attachment=True, download_name='send_log.csv')

@app.route('/stop_campaign', methods=['POST'])
@login_required
def stop_campaign():
    # This is a placeholder. You should implement logic to stop the running campaign process.
    # For now, just log the event.
    log_audit('Campaign STOP requested by user.')
    # You may want to use a process manager or set a flag checked by the campaign loop.
    return redirect(url_for('dashboard'))

# ===================== ADDED ROUTE STUBS =====================

@app.route('/campaigns')
def list_campaigns():
    """List all campaigns."""
    return "List of all campaigns (stub)"

@app.route('/campaigns/<int:campaign_id>')
def campaign_details(campaign_id):
    """View details of a specific campaign."""
    return f"Details for campaign {campaign_id} (stub)"

@app.route('/emails/sent')
def emails_sent():
    """List all sent emails."""
    return "List of sent emails (stub)"

@app.route('/emails/failed')
def emails_failed():
    """List all failed emails."""
    return "List of failed emails (stub)"

@app.route('/emails/<int:email_id>')
def email_details(email_id):
    """View details of a specific email."""
    return f"Details for email {email_id} (stub)"

@app.route('/analytics')
def analytics():
    """View analytics and performance metrics."""
    return "Analytics dashboard (stub)"

@app.route('/analytics/export')
def analytics_export():
    """Download analytics/report as Excel."""
    return "Download analytics report (stub)"

@app.route('/audit_log')
def audit_log():
    """View/download audit logs."""
    return "Audit log (stub)"

@app.route('/db/sync')
def db_sync():
    """Synchronize databases."""
    return "Database sync (stub)"

@app.route('/db/verify')
def db_verify():
    """Verify database consistency."""
    return "Database verify (stub)"

@app.route('/db/fix')
def db_fix():
    """Attempt to fix database issues."""
    return "Database fix (stub)"

@app.route('/db/cleanup')
def db_cleanup():
    """Clean up old data."""
    return "Database cleanup (stub)"

@app.route('/settings')
def settings():
    """View system settings/configuration."""
    return "Settings page (stub)"

@app.route('/accounts')
def accounts():
    """Manage email accounts."""
    return "Accounts management (stub)"

@app.route('/templates')
def templates():
    """List available email templates."""
    return "Templates list (stub)"

@app.route('/templates/<template_name>')
def template_details(template_name):
    """View template details."""
    return f"Details for template {template_name} (stub)"

# API endpoints (GET only, for AJAX/JS dashboards)
@app.route('/api/campaigns')
def api_campaigns():
    """API: Get campaigns data."""
    return "API campaigns data (stub)"

@app.route('/api/emails')
def api_emails():
    """API: Get emails data."""
    return "API emails data (stub)"

@app.route('/api/analytics')
def api_analytics():
    """API: Get analytics data."""
    return "API analytics data (stub)"

@app.route('/api/settings')
def api_settings():
    """API: Get settings data."""
    return "API settings data (stub)"

# =================== END ADDED ROUTE STUBS ===================

def keep_alive():
    """Keep the server alive by pinging itself every minute"""
    while True:
        try:
            base_url = os.environ.get('RENDER_EXTERNAL_URL', 'http://localhost:10000')
            requests.get(f"{base_url}/", timeout=10)
        except Exception as e:
            print(f"[Keep-Alive] Error pinging server: {e}")
        time.sleep(60)

def seconds_until_next_scheduled_time():
    now = datetime.now(IST)
    next_run = now.replace(hour=SCHEDULE_HOUR, minute=SCHEDULE_MINUTE, second=0, microsecond=0)
    if now >= next_run:
        next_run += timedelta(days=1)
    return (next_run - now).total_seconds()

def log_audit(message):
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(f"{datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')} - {message}\n")

def run_campaign():
    last_run_info['start'] = datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')
    last_run_info['error'] = None
    log_audit('Campaign STARTED')
    try:
        subprocess.run([
            "python", "src/main.py",
            "--resume", "data/Ayush_Srivastava.pdf",
            "--batch-size", "5",
            "--daily-limit", "1001"
        ], check=True)
    except Exception as e:
        last_run_info['error'] = str(e)
        log_audit(f'Campaign ERROR: {e}')
    last_run_info['end'] = datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')
    log_audit('Campaign ENDED')

def scheduler_loop():
    while True:
        wait_seconds = seconds_until_next_scheduled_time()
        # Check if the next run is on a weekend (Saturday=5, Sunday=6)
        from datetime import datetime, timedelta
        now = datetime.now(IST)
        next_run = now.replace(hour=SCHEDULE_HOUR, minute=SCHEDULE_MINUTE, second=0, microsecond=0)
        if now >= next_run:
            next_run += timedelta(days=1)
        # If next_run is Saturday or Sunday, skip to Monday
        while next_run.weekday() in (5, 6):
            next_run += timedelta(days=1)
        wait_seconds = (next_run - now).total_seconds()
        print(f"[Scheduler] Waiting {wait_seconds/3600:.2f} hours until next run at {next_run.strftime('%A %H:%M:%S')} IST...")
        time.sleep(wait_seconds)
        # Double-check it's not weekend before running
        if datetime.now(IST).weekday() not in (5, 6):
            print(f"[Scheduler] Starting campaign at {datetime.now(IST).strftime('%A %H:%M:%S')} IST!")
            run_campaign()
        else:
            print("[Scheduler] Skipping campaign run on weekend.")
        time.sleep(60)

if __name__ == "__main__":
    # Start the keep-alive thread
    keep_alive_thread = threading.Thread(target=keep_alive, daemon=True)
    keep_alive_thread.start()
    # Start the scheduler in a background thread
    scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
    scheduler_thread.start()
    # Start the Flask status server
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port) 