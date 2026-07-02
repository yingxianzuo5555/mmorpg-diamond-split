import sqlite3
import os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'diamond.db')

def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    # Ensure data directory exists
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    cursor = conn.cursor()

    cursor.executescript('''
        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            game_name TEXT NOT NULL DEFAULT '',
            description TEXT DEFAULT '',
            default_income_method TEXT DEFAULT 'deduct',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            is_active INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            role TEXT DEFAULT 'member',
            can_deposit INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (team_id) REFERENCES teams(id),
            UNIQUE(team_id, name)
        );

        CREATE TABLE IF NOT EXISTS boss_kills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER NOT NULL,
            boss_name TEXT NOT NULL,
            kill_time TEXT DEFAULT (datetime('now','localtime')),
            raid_leader TEXT DEFAULT '',
            screenshot TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (team_id) REFERENCES teams(id)
        );

        CREATE TABLE IF NOT EXISTS loot_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kill_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            item_quantity INTEGER DEFAULT 1,
            item_value INTEGER DEFAULT 0,
            winner_id INTEGER,
            distribution_method TEXT DEFAULT 'split',
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (kill_id) REFERENCES boss_kills(id),
            FOREIGN KEY (winner_id) REFERENCES members(id)
        );

        CREATE TABLE IF NOT EXISTS split_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER NOT NULL,
            kill_id INTEGER,
            title TEXT NOT NULL,
            total_diamond INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            income_method TEXT DEFAULT 'deduct',
            created_by TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            completed_at TEXT,
            FOREIGN KEY (team_id) REFERENCES teams(id),
            FOREIGN KEY (kill_id) REFERENCES boss_kills(id)
        );

        CREATE TABLE IF NOT EXISTS split_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            member_id INTEGER NOT NULL,
            diamond_amount INTEGER DEFAULT 0,
            dkp_used INTEGER DEFAULT 0,
            notes TEXT DEFAULT '',
            FOREIGN KEY (order_id) REFERENCES split_orders(id),
            FOREIGN KEY (member_id) REFERENCES members(id)
        );

        CREATE TABLE IF NOT EXISTS wallets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            balance INTEGER DEFAULT 0,
            total_deposited INTEGER DEFAULT 0,
            total_withdrawn INTEGER DEFAULT 0,
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (member_id) REFERENCES members(id),
            UNIQUE(member_id)
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER NOT NULL,
            member_id INTEGER,
            type TEXT NOT NULL,
            amount INTEGER NOT NULL,
            balance_after INTEGER DEFAULT 0,
            related_order_id INTEGER,
            description TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (team_id) REFERENCES teams(id),
            FOREIGN KEY (member_id) REFERENCES members(id)
        );

        CREATE TABLE IF NOT EXISTS auctions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            item_quantity INTEGER DEFAULT 1,
            starting_bid INTEGER DEFAULT 0,
            current_bid INTEGER DEFAULT 0,
            current_bidder_id INTEGER,
            min_increment INTEGER DEFAULT 100,
            status TEXT DEFAULT 'active',
            winner_id INTEGER,
            final_price INTEGER DEFAULT 0,
            created_by_id INTEGER,
            started_at TEXT DEFAULT (datetime('now','localtime')),
            ended_at TEXT,
            FOREIGN KEY (team_id) REFERENCES teams(id),
            FOREIGN KEY (current_bidder_id) REFERENCES members(id),
            FOREIGN KEY (winner_id) REFERENCES members(id)
        );

        CREATE TABLE IF NOT EXISTS bids (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            auction_id INTEGER NOT NULL,
            member_id INTEGER NOT NULL,
            bid_amount INTEGER NOT NULL,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (auction_id) REFERENCES auctions(id),
            FOREIGN KEY (member_id) REFERENCES members(id)
        );

        CREATE TABLE IF NOT EXISTS dkp_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            team_id INTEGER NOT NULL,
            dkp INTEGER DEFAULT 0,
            reason TEXT DEFAULT '',
            related_kill_id INTEGER,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (member_id) REFERENCES members(id),
            FOREIGN KEY (team_id) REFERENCES teams(id)
        );

        CREATE TABLE IF NOT EXISTS team_fund (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER NOT NULL,
            total_income INTEGER DEFAULT 0,
            total_expense INTEGER DEFAULT 0,
            balance INTEGER DEFAULT 0,
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (team_id) REFERENCES teams(id),
            UNIQUE(team_id)
        );

        CREATE TABLE IF NOT EXISTS fund_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            amount INTEGER NOT NULL,
            balance_after INTEGER DEFAULT 0,
            description TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (team_id) REFERENCES teams(id)
        );

        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER,
            setting_key TEXT NOT NULL,
            setting_value TEXT DEFAULT '',
            UNIQUE(team_id, setting_key)
        );
    ''')

    conn.commit()
    conn.close()

def init_demo_data():
    conn = get_db()
    cursor = conn.cursor()
    # Check if demo team exists
    team = cursor.execute("SELECT id FROM teams WHERE name=?", ['Demo血盟']).fetchone()
    if team:
        conn.close()
        return

    cursor.execute("INSERT INTO teams (name, game_name, description) VALUES (?,?,?)",
                   ['Demo血盟', '天堂W', '這是示範血盟'])
    team_id = cursor.lastrowid

    members_data = [
        ('盟主小明', 'leader', 1),
        ('會計小華', 'accountant', 1),
        ('打手阿強', 'member', 0),
        ('補師美美', 'member', 0),
        ('法師大雄', 'member', 0),
        ('騎士阿Ben', 'member', 0),
    ]
    for name, role, can_deposit in members_data:
        cursor.execute("INSERT INTO members (team_id, name, role, can_deposit) VALUES (?,?,?,?)",
                       [team_id, name, role, can_deposit])
        member_id = cursor.lastrowid
        cursor.execute("INSERT INTO wallets (member_id, balance) VALUES (?,0)", [member_id])

    cursor.execute("INSERT INTO team_fund (team_id, balance) VALUES (?,0)", [team_id])
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    init_demo_data()
    print("Database initialized successfully!")
