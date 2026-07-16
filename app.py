from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from models import get_db, init_db, init_demo_data
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import json

app = Flask(__name__)
app.secret_key = 'mmorpg-diamond-split-secret-key-2024'

# ==================== Helper ====================

def get_team(team_id):
    db = get_db()
    team = db.execute("SELECT * FROM teams WHERE id=?", [team_id]).fetchone()
    db.close()
    return team

def get_members(team_id):
    db = get_db()
    members = db.execute("SELECT * FROM members WHERE team_id=? AND is_active=1 ORDER BY role, name", [team_id]).fetchall()
    db.close()
    return [dict(m) for m in members]

def get_wallet(member_id):
    db = get_db()
    wallet = db.execute("SELECT * FROM wallets WHERE member_id=?", [member_id]).fetchone()
    if not wallet:
        db.execute("INSERT INTO wallets (member_id, balance) VALUES (?,0)", [member_id])
        db.commit()
        wallet = db.execute("SELECT * FROM wallets WHERE member_id=?", [member_id]).fetchone()
    db.close()
    return dict(wallet)

def log_transaction(team_id, member_id, type_, amount, balance_after, description, related_order_id=None, db=None):
    if db is None:
        db = get_db()
        should_close = True
    else:
        should_close = False
    db.execute(
        "INSERT INTO transactions (team_id, member_id, type, amount, balance_after, description, related_order_id) VALUES (?,?,?,?,?,?,?)",
        [team_id, member_id, type_, amount, balance_after, description, related_order_id]
    )
    if should_close:
        db.commit()
        db.close()


# ==================== Auth Helpers ====================
from functools import wraps

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'member_id' not in session:
            return redirect(url_for('login_page', next=request.path))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'member_id' not in session:
            return redirect(url_for('login_page', next=request.path))
        member_id = session['member_id']
        db = get_db()
        member = db.execute("SELECT role FROM members WHERE id=?", [member_id]).fetchone()
        db.close()
        if not member or member['role'] not in ('leader', 'accountant'):
            return jsonify({'error': '需要管理員或會計權限'}), 403
        return f(*args, **kwargs)
    return decorated

def get_current_member():
    if 'member_id' in session:
        db = get_db()
        m = db.execute("SELECT * FROM members WHERE id=?", [session['member_id']]).fetchone()
        db.close()
        return dict(m) if m else None
    return None

def is_admin(team_id=None):
    m = get_current_member()
    if not m:
        return False
    if team_id and m['team_id'] != team_id:
        return False
    return m['role'] in ('leader', 'accountant')

# ==================== Routes ====================

@app.route('/')
def index():
    db = get_db()
    teams = db.execute("SELECT * FROM teams WHERE is_active=1 ORDER BY id").fetchall()
    db.close()
    if not teams:
        return redirect(url_for('create_team_page'))
    return render_template('index.html', teams=[dict(t) for t in teams], current_member=get_current_member())


@app.route('/login')
def login_page():
    db = get_db()
    teams_list = db.execute("SELECT id, name FROM teams WHERE is_active=1").fetchall()
    db.close()
    return render_template('login.html', current_member=get_current_member(), teams=[dict(t) for t in teams_list])

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    name = data.get('name', '').strip()
    password = data.get('password', '')
    team_id = data.get('team_id')
    if not name:
        return jsonify({'error': '請輸入名稱'}), 400
    db = get_db()
    if team_id:
        member = db.execute("SELECT * FROM members WHERE name=? AND team_id=? AND is_active=1", [name, team_id]).fetchone()
    else:
        member = db.execute("SELECT * FROM members WHERE name=? AND is_active=1", [name]).fetchone()
    if not member:
        db.close()
        return jsonify({'error': '用戶不存在'}), 404
    # Check password
    pw = member['password_hash'] or ''
    if pw and not check_password_hash(pw, password):
        # Legacy mode: if password is set but wrong
        if password == pw:  # Allow plain text fallback for migration
            pass
        else:
            db.close()
            return jsonify({'error': '密碼錯誤'}), 401
    elif pw and not check_password_hash(pw, password):
        db.close()
        return jsonify({'error': '密碼錯誤'}), 401
    session['member_id'] = member['id']
    session['team_id'] = member['team_id']
    db.close()
    return jsonify({'success': True, 'member': dict(member), 'team_id': member['team_id']})

@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.json
    team_id = data.get('team_id')
    name = data.get('name', '').strip()
    password = data.get('password', '')
    if not name or not team_id:
        return jsonify({'error': '請填寫完整資訊'}), 400
    db = get_db()
    # Check if name exists in team
    existing = db.execute("SELECT id FROM members WHERE name=? AND team_id=? AND is_active=1", [name, team_id]).fetchone()
    if existing:
        db.close()
        return jsonify({'error': '該名稱已在團隊中'}), 400
    # Check team exists
    team = db.execute("SELECT id FROM teams WHERE id=? AND is_active=1", [team_id]).fetchone()
    if not team:
        db.close()
        return jsonify({'error': '團隊不存在'}), 404
    # Create member
    pw_hash = generate_password_hash(password) if password else ''
    cur = db.execute("INSERT INTO members (team_id, name, role, password_hash) VALUES (?,?,?,?)",
                   [team_id, name, 'member', pw_hash])
    member_id = cur.lastrowid
    db.execute("INSERT INTO wallets (member_id, balance) VALUES (?,0)", [member_id])
    db.commit()
    db.close()
    session['member_id'] = member_id
    session['team_id'] = team_id
    return jsonify({'success': True, 'member_id': member_id, 'team_id': team_id})

@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/team/create', methods=['GET'])
def create_team_page():
    return render_template('team_create.html', current_member=get_current_member())

@app.route('/api/team/create', methods=['POST'])
def api_create_team():
    data = request.json
    name = data.get('name')
    game = data.get('game_name', '')
    desc = data.get('description', '')
    leader = data.get('leader_name', '')
    if not name or not leader:
        return jsonify({'error': '請填寫團隊名稱和第一管理員'}), 400
    db = get_db()
    try:
        cur = db.execute("INSERT INTO teams (name, game_name, description) VALUES (?,?,?)", [name, game, desc])
        team_id = cur.lastrowid
        cur = db.execute("INSERT INTO members (team_id, name, role, can_deposit) VALUES (?,?,?,?)",
                   [team_id, leader, 'leader', 1])
        leader_id = cur.lastrowid
        db.execute("INSERT INTO wallets (member_id, balance) VALUES (?,0)", [leader_id])
        db.execute("INSERT INTO team_fund (team_id, balance) VALUES (?,0)", [team_id])
        db.commit()
        db.close()
        return jsonify({'success': True, 'team_id': team_id})
    except Exception as e:
        db.close()
        return jsonify({'error': str(e)}), 400

@app.route('/team/<int:team_id>')
def team_dashboard(team_id):
    team = get_team(team_id)
    if not team:
        return redirect(url_for('index'))
    team = dict(team)
    members = get_members(team_id)
    db = get_db()

    # Stats
    total_kills = db.execute("SELECT COUNT(*) as c FROM boss_kills WHERE team_id=?", [team_id]).fetchone()['c']
    total_orders = db.execute("SELECT COUNT(*) as c FROM split_orders WHERE team_id=?", [team_id]).fetchone()['c']
    total_dkp = db.execute("SELECT COALESCE(SUM(dkp),0) as s FROM dkp_records WHERE team_id=?", [team_id]).fetchone()['s']

    fund = db.execute("SELECT * FROM team_fund WHERE team_id=?", [team_id]).fetchone()
    fund = dict(fund) if fund else {'balance': 0, 'total_income': 0, 'total_expense': 0}

    recent_kills = db.execute(
        "SELECT bk.*, (SELECT COUNT(*) FROM loot_items WHERE kill_id=bk.id) as loot_count FROM boss_kills bk WHERE bk.team_id=? ORDER BY bk.kill_time DESC LIMIT 5",
        [team_id]
    ).fetchall()

    recent_orders = db.execute(
        "SELECT so.*, (SELECT COUNT(*) FROM split_details WHERE order_id=so.id) as member_count FROM split_orders so WHERE so.team_id=? ORDER BY so.created_at DESC LIMIT 5",
        [team_id]
    ).fetchall()

    db.close()
    current = get_current_member()
    return render_template('dashboard.html',
                         team=team, members=members, current_member=current,
                         total_kills=total_kills, total_orders=total_orders,
                         total_dkp=total_dkp, fund=fund,
                         recent_kills=[dict(r) for r in recent_kills],
                         recent_orders=[dict(r) for r in recent_orders])

# ==================== Team Members API ====================

@app.route('/api/team/<int:team_id>/members', methods=['GET'])
def api_get_members(team_id):
    return jsonify(get_members(team_id))

@app.route('/api/team/<int:team_id>/members', methods=['POST'])
def api_add_member(team_id):
    data = request.json
    name = data.get('name')
    role = data.get('role', 'member')
    can_deposit = data.get('can_deposit', 0)
    if not name:
        return jsonify({'error': '請填寫成員名稱'}), 400
    db = get_db()
    try:
        cur = db.execute("INSERT INTO members (team_id, name, role, can_deposit) VALUES (?,?,?,?)",
                   [team_id, name, role, can_deposit])
        member_id = cur.lastrowid
        db.execute("INSERT INTO wallets (member_id, balance) VALUES (?,0)", [member_id])
        db.commit()
        db.close()
        return jsonify({'success': True, 'member_id': member_id})
    except Exception as e:
        db.close()
        return jsonify({'error': str(e)}), 400

@app.route('/api/team/<int:team_id>/members/<int:member_id>', methods=['PUT'])
def api_update_member(team_id, member_id):
    data = request.json
    db = get_db()
    db.execute("UPDATE members SET role=?, can_deposit=? WHERE id=? AND team_id=?",
               [data.get('role', 'member'), data.get('can_deposit', 0), member_id, team_id])
    db.commit()
    db.close()
    return jsonify({'success': True})

@app.route('/api/team/<int:team_id>/members/<int:member_id>', methods=['DELETE'])
def api_delete_member(team_id, member_id):
    db = get_db()
    db.execute("UPDATE members SET is_active=0 WHERE id=? AND team_id=?", [member_id, team_id])
    db.commit()
    db.close()
    return jsonify({'success': True})

# ==================== Boss Kill & Loot ====================

@app.route('/team/<int:team_id>/boss')
def boss_page(team_id):
    team = dict(get_team(team_id))
    members = get_members(team_id)
    current = get_current_member()
    db = get_db()
    kills = db.execute(
        """SELECT bk.*, 
           (SELECT COUNT(*) FROM loot_items WHERE kill_id=bk.id) as loot_count,
           (SELECT COUNT(*) FROM boss_participants WHERE kill_id=bk.id) as participant_count
           FROM boss_kills bk WHERE bk.team_id=? ORDER BY bk.kill_time DESC""",
        [team_id]
    ).fetchall()
    db.close()
    return render_template('boss.html', team=team, members=members, kills=[dict(k) for k in kills], current_member=current)

@app.route('/api/team/<int:team_id>/boss/kill', methods=['POST'])
def api_create_kill(team_id):
    data = request.json
    db = get_db()
    cur = db.execute(
        "INSERT INTO boss_kills (team_id, boss_name, raid_leader, notes) VALUES (?,?,?,?)",
        [team_id, data['boss_name'], data.get('raid_leader', ''), data.get('notes', '')]
    )
    kill_id = cur.lastrowid
    # Auto-create split order
    db.execute(
        "INSERT INTO split_orders (team_id, kill_id, title, created_by) VALUES (?,?,?,?)",
        [team_id, kill_id, f"【{data['boss_name']}】掉落分配", data.get('raid_leader', '')]
    )
    db.commit()
    db.close()
    return jsonify({'success': True, 'kill_id': kill_id})

@app.route('/api/team/<int:team_id>/boss/<int:kill_id>', methods=['GET'])
def api_get_kill(team_id, kill_id):
    db = get_db()
    kill = db.execute("SELECT * FROM boss_kills WHERE id=? AND team_id=?", [kill_id, team_id]).fetchone()
    items = db.execute(
        "SELECT li.*, m.name as winner_name FROM loot_items li LEFT JOIN members m ON li.winner_id=m.id WHERE li.kill_id=? ORDER BY li.id",
        [kill_id]
    ).fetchall()
    participants = db.execute(
        "SELECT bp.*, m.name as member_name FROM boss_participants bp JOIN members m ON bp.member_id=m.id WHERE bp.kill_id=?",
        [kill_id]
    ).fetchall()
    all_members = db.execute("SELECT id, name FROM members WHERE team_id=? AND is_active=1 ORDER BY name", [team_id]).fetchall()
    db.close()
    return jsonify({
        'kill': dict(kill),
        'items': [dict(i) for i in items],
        'participants': [dict(p) for p in participants],
        'all_members': [dict(m) for m in all_members]
    })

@app.route('/api/team/<int:team_id>/boss/<int:kill_id>/loot', methods=['POST'])
def api_add_loot(team_id, kill_id):
    data = request.json
    db = get_db()
    db.execute(
        "INSERT INTO loot_items (kill_id, item_name, item_quantity, item_value, winner_id, distribution_method, status) VALUES (?,?,?,?,?,?,?)",
        [kill_id, data['item_name'], data.get('quantity', 1), data.get('value', 0),
         data.get('winner_id'), data.get('method', 'split'), 'pending']
    )
    db.commit()
    db.close()
    return jsonify({'success': True})

@app.route('/api/team/<int:team_id>/boss/<int:kill_id>/loot/<int:item_id>', methods=['DELETE'])
def api_delete_loot(team_id, kill_id, item_id):
    db = get_db()
    db.execute("DELETE FROM loot_items WHERE id=? AND kill_id=?", [item_id, kill_id])
    db.commit()
    db.close()
    return jsonify({'success': True})


@app.route('/api/team/<int:team_id>/boss/<int:kill_id>/participants', methods=['GET'])
def api_get_participants(team_id, kill_id):
    db = get_db()
    participants = db.execute(
        "SELECT bp.*, m.name as member_name FROM boss_participants bp JOIN members m ON bp.member_id=m.id WHERE bp.kill_id=?",
        [kill_id]
    ).fetchall()
    # Also return all active members for selection
    all_members = db.execute("SELECT id, name FROM members WHERE team_id=? AND is_active=1 ORDER BY name", [team_id]).fetchall()
    db.close()
    return jsonify({
        'participants': [dict(p) for p in participants],
        'all_members': [dict(m) for m in all_members]
    })

@app.route('/api/team/<int:team_id>/boss/<int:kill_id>/participants', methods=['POST'])
def api_set_participants(team_id, kill_id):
    if not is_admin(team_id):
        return jsonify({'error': '權限不足'}), 403
    data = request.json
    member_ids = data.get('member_ids', [])
    db = get_db()
    # Clear existing
    db.execute("DELETE FROM boss_participants WHERE kill_id=?", [kill_id])
    # Add new
    for mid in member_ids:
        db.execute("INSERT OR IGNORE INTO boss_participants (kill_id, member_id) VALUES (?,?)", [kill_id, mid])
    db.commit()
    db.close()
    return jsonify({'success': True})

@app.route('/api/team/<int:team_id>/boss/<int:kill_id>', methods=['PUT'])
def api_update_kill(team_id, kill_id):
    if not is_admin(team_id):
        return jsonify({'error': '權限不足'}), 403
    data = request.json
    db = get_db()
    db.execute(
        "UPDATE boss_kills SET boss_name=?, raid_leader=?, notes=? WHERE id=? AND team_id=?",
        [data.get('boss_name'), data.get('raid_leader', ''), data.get('notes', ''), kill_id, team_id]
    )
    db.commit()
    db.close()
    return jsonify({'success': True})

@app.route('/api/team/<int:team_id>/loot/<int:item_id>', methods=['PUT'])
def api_update_loot(team_id, item_id):
    if not is_admin(team_id):
        return jsonify({'error': '權限不足'}), 403
    data = request.json
    db = get_db()
    db.execute(
        "UPDATE loot_items SET item_name=?, item_quantity=?, item_value=?, distribution_method=?, winner_id=? WHERE id=?",
        [data.get('item_name'), data.get('quantity', 1), data.get('value', 0),
         data.get('method', 'split'), data.get('winner_id'), item_id]
    )
    db.commit()
    db.close()
    return jsonify({'success': True})

@app.route('/api/team/<int:team_id>/dkp/<int:dkp_id>', methods=['PUT'])
def api_update_dkp(team_id, dkp_id):
    if not is_admin(team_id):
        return jsonify({'error': '權限不足'}), 403
    data = request.json
    db = get_db()
    db.execute(
        "UPDATE dkp_records SET dkp=?, reason=? WHERE id=? AND team_id=?",
        [data.get('dkp'), data.get('reason', ''), dkp_id, team_id]
    )
    db.commit()
    db.close()
    return jsonify({'success': True})

@app.route('/api/team/<int:team_id>/dkp/<int:dkp_id>', methods=['DELETE'])
def api_delete_dkp(team_id, dkp_id):
    if not is_admin(team_id):
        return jsonify({'error': '權限不足'}), 403
    db = get_db()
    db.execute("DELETE FROM dkp_records WHERE id=? AND team_id=?", [dkp_id, team_id])
    db.commit()
    db.close()
    return jsonify({'success': True})

# ==================== Split Orders ====================

@app.route('/team/<int:team_id>/orders')
def orders_page(team_id):
    team = dict(get_team(team_id))
    members = get_members(team_id)
    db = get_db()
    orders = db.execute(
        """SELECT so.*, bk.boss_name,
           (SELECT COUNT(*) FROM split_details WHERE order_id=so.id) as member_count
           FROM split_orders so
           LEFT JOIN boss_kills bk ON so.kill_id=bk.id
           WHERE so.team_id=?
           ORDER BY so.created_at DESC""",
        [team_id]
    ).fetchall()
    db.close()
    current = get_current_member()
    return render_template('orders.html', team=team, members=members, orders=[dict(o) for o in orders], current_member=current)

@app.route('/api/team/<int:team_id>/orders/<int:order_id>', methods=['GET'])
def api_get_order(team_id, order_id):
    db = get_db()
    order = db.execute(
        "SELECT so.*, bk.boss_name FROM split_orders so LEFT JOIN boss_kills bk ON so.kill_id=bk.id WHERE so.id=? AND so.team_id=?",
        [order_id, team_id]
    ).fetchone()
    details = db.execute(
        "SELECT sd.*, m.name as member_name FROM split_details sd JOIN members m ON sd.member_id=m.id WHERE sd.order_id=? ORDER BY sd.id",
        [order_id]
    ).fetchall()
    db.close()
    return jsonify({'order': dict(order), 'details': [dict(d) for d in details]})

@app.route('/api/team/<int:team_id>/orders/<int:order_id>/distribute', methods=['POST'])
def api_distribute_order(team_id, order_id):
    """Distribute diamonds to members"""
    data = request.json
    db = get_db()
    order = db.execute("SELECT * FROM split_orders WHERE id=? AND team_id=?", [order_id, team_id]).fetchone()
    if not order:
        db.close()
        return jsonify({'error': '訂單不存在'}), 404

    # Clear old details
    db.execute("DELETE FROM split_details WHERE order_id=?", [order_id])

    total = 0
    for item in data['distributions']:
        member_id = item['member_id']
        amount = item['amount']
        dkp_used = item.get('dkp_used', 0)
        if amount > 0:
            db.execute(
                "INSERT INTO split_details (order_id, member_id, diamond_amount, dkp_used) VALUES (?,?,?,?)",
                [order_id, member_id, amount, dkp_used]
            )
            total += amount

    db.execute("UPDATE split_orders SET total_diamond=?, status=?, income_method=? WHERE id=?",
               [total, data.get('status', 'pending'), data.get('income_method', 'deduct'), order_id])

    # If completed, process wallet deductions
    if data.get('status') == 'completed':
        income_method = data.get('income_method', 'deduct')
        details = db.execute(
            "SELECT sd.*, m.name FROM split_details sd JOIN members m ON sd.member_id=m.id WHERE sd.order_id=?",
            [order_id]
        ).fetchall()
        for d in details:
            wallet = get_wallet(d['member_id'])
            if income_method == 'deduct':
                new_balance = wallet['balance'] - d['diamond_amount']
                db.execute("UPDATE wallets SET balance=?, total_withdrawn=total_withdrawn+?, updated_at=datetime('now','localtime') WHERE member_id=?",
                           [new_balance, d['diamond_amount'], d['member_id']])
                log_transaction(team_id, d['member_id'], 'deduct', d['diamond_amount'], new_balance,
                              f"分鑽扣除: {order['title']}", order_id, db=db)

        # Update team fund
        fund = db.execute("SELECT * FROM team_fund WHERE team_id=?", [team_id]).fetchone()
        if fund:
            new_balance = fund['balance'] + total
            db.execute("UPDATE team_fund SET total_income=total_income+?, balance=?, updated_at=datetime('now','localtime') WHERE team_id=?",
                       [total, new_balance, team_id])
        db.execute("UPDATE split_orders SET completed_at=datetime('now','localtime') WHERE id=?", [order_id])

    db.commit()
    db.close()
    return jsonify({'success': True})

@app.route('/api/team/<int:team_id>/orders/<int:order_id>/status', methods=['PUT'])
def api_update_order_status(team_id, order_id):
    data = request.json
    db = get_db()
    status = data.get('status')
    if status == 'completed':
        db.execute("UPDATE split_orders SET status=?, completed_at=datetime('now','localtime') WHERE id=? AND team_id=?",
                   [status, order_id, team_id])
    else:
        db.execute("UPDATE split_orders SET status=? WHERE id=? AND team_id=?", [status, order_id, team_id])
    db.commit()
    db.close()
    return jsonify({'success': True})

# ==================== Wallet ====================

@app.route('/team/<int:team_id>/wallet')
def wallet_page(team_id):
    team = dict(get_team(team_id))
    members = get_members(team_id)
    db = get_db()
    wallets_data = []
    for m in members:
        w = get_wallet(m['id'])
        wallets_data.append({**m, **w})
    fund = db.execute("SELECT * FROM team_fund WHERE team_id=?", [team_id]).fetchone()
    fund = dict(fund) if fund else {'balance': 0, 'total_income': 0, 'total_expense': 0}
    db.close()
    current = get_current_member()
    return render_template('wallet.html', team=team, wallets=wallets_data, fund=fund, current_member=current)

@app.route('/api/team/<int:team_id>/wallet/deposit', methods=['POST'])
def api_wallet_deposit(team_id):
    """Deposit diamonds to a member's wallet"""
    data = request.json
    member_id = data['member_id']
    amount = data['amount']
    db = get_db()
    wallet = get_wallet(member_id)
    new_balance = wallet['balance'] + amount
    db.execute("UPDATE wallets SET balance=?, total_deposited=total_deposited+?, updated_at=datetime('now','localtime') WHERE member_id=?",
               [new_balance, amount, member_id])
    log_transaction(team_id, member_id, 'deposit', amount, new_balance, data.get('description', '儲值'), db=db)
    db.commit()
    db.close()
    return jsonify({'success': True})

@app.route('/api/team/<int:team_id>/wallet/withdraw', methods=['POST'])
def api_wallet_withdraw(team_id):
    data = request.json
    member_id = data['member_id']
    amount = data['amount']
    db = get_db()
    wallet = get_wallet(member_id)
    if wallet['balance'] < amount:
        db.close()
        return jsonify({'error': '餘額不足'}), 400
    new_balance = wallet['balance'] - amount
    db.execute("UPDATE wallets SET balance=?, total_withdrawn=total_withdrawn+?, updated_at=datetime('now','localtime') WHERE member_id=?",
               [new_balance, amount, member_id])
    log_transaction(team_id, member_id, 'withdraw', amount, new_balance, data.get('description', '提領'), db=db)
    db.commit()
    db.close()
    return jsonify({'success': True})

@app.route('/api/team/<int:team_id>/wallet/transactions', methods=['GET'])
def api_wallet_transactions(team_id):
    member_id = request.args.get('member_id')
    db = get_db()
    if member_id:
        txns = db.execute(
            "SELECT t.*, m.name as member_name FROM transactions t LEFT JOIN members m ON t.member_id=m.id WHERE t.team_id=? AND t.member_id=? ORDER BY t.created_at DESC LIMIT 100",
            [team_id, member_id]
        ).fetchall()
    else:
        txns = db.execute(
            "SELECT t.*, m.name as member_name FROM transactions t LEFT JOIN members m ON t.member_id=m.id WHERE t.team_id=? ORDER BY t.created_at DESC LIMIT 100",
            [team_id]
        ).fetchall()
    db.close()
    return jsonify([dict(t) for t in txns])

# ==================== Auction ====================

@app.route('/team/<int:team_id>/auction')
def auction_page(team_id):
    team = dict(get_team(team_id))
    members = get_members(team_id)
    db = get_db()
    auctions = db.execute(
        """SELECT a.*, 
           COALESCE(cm.name, '') as current_bidder_name,
           COALESCE(wm.name, '') as winner_name,
           cr.name as creator_name
           FROM auctions a
           LEFT JOIN members cm ON a.current_bidder_id=cm.id
           LEFT JOIN members wm ON a.winner_id=wm.id
           LEFT JOIN members cr ON a.created_by_id=cr.id
           WHERE a.team_id=?
           ORDER BY a.status, a.started_at DESC""",
        [team_id]
    ).fetchall()
    db.close()
    current = get_current_member()
    return render_template('auction.html', team=team, members=members, auctions=[dict(a) for a in auctions], current_member=current)

@app.route('/api/team/<int:team_id>/auction/create', methods=['POST'])
def api_create_auction(team_id):
    data = request.json
    db = get_db()
    db.execute(
        "INSERT INTO auctions (team_id, item_name, item_quantity, starting_bid, current_bid, min_increment, created_by_id) VALUES (?,?,?,?,?,?,?)",
        [team_id, data['item_name'], data.get('quantity', 1), data.get('starting_bid', 0),
         data.get('starting_bid', 0), data.get('min_increment', 100), data.get('created_by_id')]
    )
    db.commit()
    db.close()
    return jsonify({'success': True})

@app.route('/api/team/<int:team_id>/auction/<int:auction_id>/bid', methods=['POST'])
def api_place_bid(team_id, auction_id):
    data = request.json
    amount = data['amount']
    member_id = data['member_id']
    db = get_db()
    auction = db.execute("SELECT * FROM auctions WHERE id=? AND team_id=?", [auction_id, team_id]).fetchone()
    if not auction or auction['status'] != 'active':
        db.close()
        return jsonify({'error': '拍賣已結束'}), 400
    if amount < auction['current_bid'] + auction['min_increment']:
        db.close()
        return jsonify({'error': f'出價需高於當前價格至少 {auction["min_increment"]}'}), 400

    wallet = get_wallet(member_id)
    if wallet['balance'] < amount:
        db.close()
        return jsonify({'error': '錢包餘額不足'}), 400

    db.execute("INSERT INTO bids (auction_id, member_id, bid_amount) VALUES (?,?,?)",
               [auction_id, member_id, amount])
    db.execute("UPDATE auctions SET current_bid=?, current_bidder_id=? WHERE id=?",
               [amount, member_id, auction_id])
    db.commit()
    db.close()
    return jsonify({'success': True})

@app.route('/api/team/<int:team_id>/auction/<int:auction_id>/end', methods=['POST'])
def api_end_auction(team_id, auction_id):
    data = request.json
    db = get_db()
    auction = db.execute("SELECT * FROM auctions WHERE id=? AND team_id=?", [auction_id, team_id]).fetchone()
    if not auction:
        db.close()
        return jsonify({'error': '不存在'}), 404

    winner_id = data.get('winner_id') or auction['current_bidder_id']
    final_price = data.get('final_price') or auction['current_bid']

    db.execute(
        "UPDATE auctions SET status='ended', winner_id=?, final_price=?, ended_at=datetime('now','localtime') WHERE id=?",
        [winner_id, final_price, auction_id]
    )

    winner = db.execute("SELECT * FROM members WHERE id=?", [winner_id]).fetchone()
    if winner:
        wallet = get_wallet(winner_id)
        new_balance = wallet['balance'] - final_price
        db.execute("UPDATE wallets SET balance=?, total_withdrawn=total_withdrawn+?, updated_at=datetime('now','localtime') WHERE member_id=?",
                   [new_balance, final_price, winner_id])
        log_transaction(team_id, winner_id, 'auction_pay', final_price, new_balance,
                      f"拍賣得標: {auction['item_name']}", auction_id, db=db)

        fund = db.execute("SELECT * FROM team_fund WHERE team_id=?", [team_id]).fetchone()
        if fund:
            new_fund_balance = fund['balance'] + final_price
            db.execute("UPDATE team_fund SET total_income=total_income+?, balance=?, updated_at=datetime('now','localtime') WHERE team_id=?",
                       [final_price, new_fund_balance, team_id])
    db.commit()
    db.close()
    return jsonify({'success': True})

@app.route('/api/team/<int:team_id>/auction/<int:auction_id>/bids', methods=['GET'])
def api_get_bids(team_id, auction_id):
    db = get_db()
    bids = db.execute(
        "SELECT b.*, m.name as bidder_name FROM bids b JOIN members m ON b.member_id=m.id WHERE b.auction_id=? ORDER BY b.created_at DESC",
        [auction_id]
    ).fetchall()
    db.close()
    return jsonify([dict(b) for b in bids])

# ==================== DKP ====================

@app.route('/team/<int:team_id>/dkp')
def dkp_page(team_id):
    team = dict(get_team(team_id))
    members = get_members(team_id)
    db = get_db()
    dkp_summary = []
    for m in members:
        total = db.execute("SELECT COALESCE(SUM(dkp),0) as s FROM dkp_records WHERE member_id=?", [m['id']]).fetchone()['s']
        dkp_summary.append({**m, 'total_dkp': total})

    histories = db.execute(
        "SELECT d.*, m.name as member_name, bk.boss_name FROM dkp_records d LEFT JOIN members m ON d.member_id=m.id LEFT JOIN boss_kills bk ON d.related_kill_id=bk.id WHERE d.team_id=? ORDER BY d.created_at DESC LIMIT 100",
        [team_id]
    ).fetchall()
    db.close()
    current = get_current_member()
    return render_template('dkp.html', team=team, dkp_summary=dkp_summary, histories=[dict(h) for h in histories], current_member=current)

@app.route('/api/team/<int:team_id>/dkp/add', methods=['POST'])
def api_add_dkp(team_id):
    data = request.json
    db = get_db()
    db.execute(
        "INSERT INTO dkp_records (member_id, team_id, dkp, reason, related_kill_id) VALUES (?,?,?,?,?)",
        [data['member_id'], team_id, data['dkp'], data.get('reason', ''), data.get('kill_id')]
    )
    db.commit()
    db.close()
    return jsonify({'success': True})

# ==================== Fund ====================

@app.route('/api/team/<int:team_id>/fund/transactions', methods=['GET'])
def api_fund_transactions(team_id):
    db = get_db()
    txns = db.execute(
        "SELECT * FROM fund_transactions WHERE team_id=? ORDER BY created_at DESC LIMIT 100",
        [team_id]
    ).fetchall()
    db.close()
    return jsonify([dict(t) for t in txns])

@app.route('/api/team/<int:team_id>/fund/operate', methods=['POST'])
def api_fund_operate(team_id):
    data = request.json
    amount = data['amount']
    op_type = data['type']  # income or expense
    desc = data.get('description', '')
    db = get_db()
    fund = db.execute("SELECT * FROM team_fund WHERE team_id=?", [team_id]).fetchone()
    if not fund:
        db.execute("INSERT INTO team_fund (team_id, balance) VALUES (?,0)", [team_id])
        fund = db.execute("SELECT * FROM team_fund WHERE team_id=?", [team_id]).fetchone()

    if op_type == 'expense' and fund['balance'] < amount:
        db.close()
        return jsonify({'error': '公基金餘額不足'}), 400

    new_balance = fund['balance'] + (amount if op_type == 'income' else -amount)
    if op_type == 'income':
        db.execute("UPDATE team_fund SET total_income=total_income+?, balance=?, updated_at=datetime('now','localtime') WHERE team_id=?",
                   [amount, new_balance, team_id])
    else:
        db.execute("UPDATE team_fund SET total_expense=total_expense+?, balance=?, updated_at=datetime('now','localtime') WHERE team_id=?",
                   [amount, new_balance, team_id])

    db.execute(
        "INSERT INTO fund_transactions (team_id, type, amount, balance_after, description) VALUES (?,?,?,?,?)",
        [team_id, op_type, amount, new_balance, desc]
    )
    db.commit()
    db.close()
    return jsonify({'success': True})

# ==================== Settings ====================

@app.route('/team/<int:team_id>/settings')
def settings_page(team_id):
    team = dict(get_team(team_id))
    db = get_db()
    settings_list = db.execute("SELECT * FROM settings WHERE team_id=?", [team_id]).fetchall()
    settings_dict = {s['setting_key']: s['setting_value'] for s in settings_list}
    db.close()
    current = get_current_member()
    return render_template('settings.html', team=team, settings=settings_dict, current_member=current)

@app.route('/api/team/<int:team_id>/settings', methods=['POST'])
def api_update_settings(team_id):
    data = request.json
    db = get_db()
    for key, value in data.items():
        existing = db.execute("SELECT id FROM settings WHERE team_id=? AND setting_key=?", [team_id, key]).fetchone()
        if existing:
            db.execute("UPDATE settings SET setting_value=? WHERE id=?", [value, existing['id']])
        else:
            db.execute("INSERT INTO settings (team_id, setting_key, setting_value) VALUES (?,?,?)", [team_id, key, value])
    db.commit()
    db.close()
    return jsonify({'success': True})

# ==================== Reporting ====================

@app.route('/team/<int:team_id>/reports')
def reports_page(team_id):
    team = dict(get_team(team_id))
    db = get_db()

    # Monthly kill stats
    monthly_kills = db.execute(
        "SELECT strftime('%Y-%m', kill_time) as month, COUNT(*) as count, SUM(loot_count) as total_loot FROM (SELECT bk.*, (SELECT COUNT(*) FROM loot_items WHERE kill_id=bk.id) as loot_count FROM boss_kills bk WHERE bk.team_id=?) GROUP BY month ORDER BY month DESC LIMIT 12",
        [team_id]
    ).fetchall()

    # Member ranking
    member_ranking = db.execute(
        """SELECT m.name, 
           COALESCE((SELECT SUM(amount) FROM transactions WHERE member_id=m.id AND type='deduct'),0) as total_deduct,
           COALESCE((SELECT SUM(dkp) FROM dkp_records WHERE member_id=m.id),0) as total_dkp,
           COALESCE((SELECT balance FROM wallets WHERE member_id=m.id),0) as balance
           FROM members m WHERE m.team_id=? AND m.is_active=1
           ORDER BY total_dkp DESC""",
        [team_id]
    ).fetchall()

    db.close()
    current = get_current_member()
    return render_template('reports.html', team=team,
                         monthly_kills=[dict(r) for r in monthly_kills],
                         member_ranking=[dict(r) for r in member_ranking])

# ==================== Start ====================
# Initialize database on startup
init_db()
init_demo_data()


if __name__ == '__main__':
    init_db()
    init_demo_data()
    print("""
╔══════════════════════════════════════════╗
║     MMORPG 分鑽系統 v1.0                 ║
║                                          ║
║  伺服器啟動中...                          ║
║  打開瀏覽器訪問:                          ║
║  http://127.0.0.1:5000                   ║
╚══════════════════════════════════════════╝
    """)
    import os
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port, debug=False)
