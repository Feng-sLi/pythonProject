# -*- coding: utf-8 -*-
import sys
import io
import os
from datetime import datetime

# 强制UTF-8编码，彻底解决中文乱码
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
import networkx as nx
from sqlalchemy import func

# Flask初始化配置
app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False  # 关键：支持中文JSON返回
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.encoding = 'utf-8'

# 项目核心配置（仅修改你的MySQL密码）
app.secret_key = 'GOT-2025-FINAL-FIX-001'
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:123456@localhost:3306/got_db?charset=utf8mb4'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ECHO'] = False

# 路径配置
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

# 数据库 & 登录管理器初始化
from models import db, User, Favorite, History, Node, Edge, Season, NetworkMetric

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = '请先登录，才能访问该页面！'
login_manager.login_message_category = 'warning'
login_manager.session_protection = 'strong'


@login_manager.user_loader
def load_user(user_id):
    with app.app_context():
        return User.query.get(int(user_id))


# ======================== ✅ 用户认证路由（全中文提示） ========================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        with app.app_context():
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '').strip()
            user = User.query.filter_by(username=username).first()
            if user and user.check_password(password):
                login_user(user)
                flash('登录成功！', 'success')
                return redirect(url_for('index'))
            flash('用户名或密码错误！', 'danger')
    return render_template('auth/login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        with app.app_context():
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip()
            password = request.form.get('password', '').strip()
            confirm_pwd = request.form.get('confirm_pwd', '').strip()
            if password != confirm_pwd:
                flash('两次输入的密码不一致！', 'danger')
                return render_template('auth/register.html')
            if User.query.filter_by(username=username).first():
                flash('用户名已存在！', 'danger')
                return render_template('auth/register.html')
            new_user = User(username=username, email=email)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            flash('注册成功！请登录', 'success')
            return redirect(url_for('login'))
    return render_template('auth/register.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('退出登录成功！', 'success')
    return redirect(url_for('index'))


# ======================== ✅ 首页路由（节点度计算 + 核心高亮） ========================
@app.route('/')
def index():
    with app.app_context():
        seasons = Season.query.order_by(Season.season_number).all()
        nodes = Node.query.order_by(Node.english_name).all()
        edges = Edge.query.all()

        # 计算节点度，实现核心节点大小区分
        node_degree = {}
        for node in nodes:
            node_degree[node.node_id] = 0
        for edge in edges:
            node_degree[edge.source_node_id] += 1
            node_degree[edge.target_node_id] += 1

        # 预处理边数据
        for edge in edges:
            source_node = Node.query.get(edge.source_node_id)
            target_node = Node.query.get(edge.target_node_id)
            edge.source_node_name = source_node.english_name if source_node else ""
            edge.target_node_name = target_node.english_name if target_node else ""

        # 绑定度属性到节点
        for node in nodes:
            node.degree = node_degree[node.node_id]

        metrics = NetworkMetric.query.order_by(NetworkMetric.season_id).all()
    return render_template('index.html', seasons=seasons, nodes=nodes, edges=edges, metrics=metrics)


# ======================== ✅ 核心恢复：角色存活概率预测路由 ========================
@app.route('/survival_prediction', methods=['GET', 'POST'])
def survival_prediction():
    pred_result = None
    with app.app_context():
        all_nodes = Node.query.order_by(Node.english_name).all()
        all_seasons = Season.query.order_by(Season.season_number).all()

        if request.method == 'POST':
            char_name = request.form.get('char_name', '').strip()
            target_season = request.form.get('target_season', type=int)

            # 参数校验
            if not char_name or not target_season:
                flash('请选择角色和预测季数！', 'danger')
                return render_template('survival_prediction.html', nodes=all_nodes, seasons=all_seasons)

            # 查询角色数据
            target_char = Node.query.filter_by(english_name=char_name).first()
            if not target_char:
                flash('所选角色不存在！', 'danger')
                return render_template('survival_prediction.html', nodes=all_nodes, seasons=all_seasons)

            # ✅ 存活概率核心计算逻辑（贴合权游剧情+节点度加权）
            char_degree = target_char.degree if hasattr(target_char, 'degree') else 0
            # 基础存活概率：季数越大，存活概率越低；关联度越高，存活概率越高
            base_survival = 95 - (target_season * 6) + (char_degree * 3)
            survival_rate = max(5, min(98, base_survival))  # 限制区间5%-98%

            # 存活风险等级判定
            if survival_rate >= 80:
                risk_level = "极低风险 ✅"
                risk_desc = "该角色为核心角色，关联关系极多，下一季存活概率极高，大概率推动主线剧情。"
            elif survival_rate >= 50:
                risk_level = "中等风险 ⚠️"
                risk_desc = "该角色为重要配角，下一季有一定存活概率，可能因剧情冲突面临死亡风险。"
            else:
                risk_level = "极高风险 ❌"
                risk_desc = "该角色关联关系少，属于边缘角色，下一季大概率领便当，存活可能性极低。"

            # 组装预测结果
            pred_result = {
                "char_name": target_char.english_name,
                "target_season": target_season,
                "survival_rate": f"{survival_rate:.1f}%",
                "risk_level": risk_level,
                "risk_desc": risk_desc,
                "relation_count": char_degree
            }
    return render_template('survival_prediction.html', nodes=all_nodes, seasons=all_seasons, pred_result=pred_result)


# ======================== ✅ 其他业务路由（全中文适配） ========================
@app.route('/family_analysis')
def family_analysis():
    with app.app_context():
        seasons = Season.query.order_by(Season.season_number).all()
        nodes = Node.query.all()
        family_map = {
            "史塔克": ["Ned-Stark", "Jon-Snow", "Sansa-Stark", "Arya-Stark"],
            "兰尼斯特": ["Tyrion-Lannister", "Cersei-Lannister", "Jaime-Lannister"],
            "坦格利安": ["Daenerys-Targaryen", "Viserys-Targaryen"],
            "拜拉席恩": ["Robert-Baratheon", "Joffrey-Baratheon"]
        }
    return render_template('family_analysis.html', seasons=seasons, nodes=nodes, family_map=family_map)


@app.route('/api/family_analysis', methods=['POST'])
def api_family_analysis():
    with app.app_context():
        family = request.form.get("family")
        season = request.form.get("season", type=int)
        if not family or not season:
            return jsonify({"code": 0, "msg": "参数错误！"})

        family_chars = Node.query.filter(Node.english_name.like(f"%{family}%")).all()
        char_ids = [c.node_id for c in family_chars]
        edges = Edge.query.filter(Edge.season_id == season, Edge.source_node_id.in_(char_ids),
                                  Edge.target_node_id.in_(char_ids)).all()

        char_count = len(family_chars)
        rel_count = len(edges)
        core_char = family_chars[0].english_name if family_chars else "无"
        influence = round(rel_count * 8 + char_count * 5, 1)
        survival = f"{round(90 - season * 5, 1)}%"

        return jsonify({
            "code": 1,
            "data": {
                "char_count": char_count,
                "rel_count": rel_count,
                "core_char": core_char,
                "influence": influence,
                "survival": survival,
                "chars": [c.english_name for c in family_chars]
            }
        })


@app.route('/metrics')
def metrics():
    with app.app_context():
        seasons = Season.query.order_by(Season.season_number).all()
        metrics = NetworkMetric.query.all()
    return render_template('metrics.html', seasons=seasons, metrics=metrics)


@app.route('/about')
def about():
    return render_template('about.html')


# ======================== ✅ 路径查询 + 历史记录（全中文） ========================
def save_query_history(user_id, start_char, end_char, season, result):
    with app.app_context():
        new_history = History(
            user_id=user_id,
            operation='路径查询',
            content=f"起点: {start_char} | 终点: {end_char} | 季数: {season} | 结果: {result}",
            create_time=datetime.now()
        )
        db.session.add(new_history)
        db.session.commit()


@app.route('/path_query', methods=['GET', 'POST'])
def path_query():
    path_result = None
    error_msg = None
    with app.app_context():
        all_nodes = Node.query.order_by(Node.english_name).all()
        all_seasons = Season.query.order_by(Season.season_number).all()

        if request.method == 'POST':
            start_name = request.form.get('start_char', '').strip()
            end_name = request.form.get('end_char', '').strip()
            season_id = request.form.get('season', '')

            if not start_name or not end_name or not season_id:
                error_msg = "请选择完整参数（起点+终点+季数）！"
            else:
                try:
                    season_id = int(season_id)
                    start_node = Node.query.filter_by(english_name=start_name).first()
                    end_node = Node.query.filter_by(english_name=end_name).first()

                    if not start_node or not end_node:
                        error_msg = f"所选角色不存在！"
                    elif not Season.query.filter_by(season_number=season_id).first():
                        error_msg = f"第 {season_id} 季数据不存在！"
                    else:
                        valid_ids = [n.node_id for n in all_nodes]
                        edges = Edge.query.filter(Edge.season_id == season_id, Edge.source_node_id.in_(valid_ids),
                                                  Edge.target_node_id.in_(valid_ids)).all()
                        G = nx.Graph()
                        for e in edges:
                            G.add_edge(e.source_node_id, e.target_node_id)

                        if start_node.node_id not in G.nodes or end_node.node_id not in G.nodes:
                            error_msg = f"第 {season_id} 季无该角色相关数据！"
                            if current_user.is_authenticated:
                                save_query_history(current_user.id, start_name, end_name, season_id, "无数据")
                        elif not nx.has_path(G, start_node.node_id, end_node.node_id):
                            error_msg = f"{start_name} 与 {end_name} 之间无关联路径！"
                            if current_user.is_authenticated:
                                save_query_history(current_user.id, start_name, end_name, season_id, "无路径")
                        else:
                            path_ids = nx.shortest_path(G, start_node.node_id, end_node.node_id)
                            path_result = [Node.query.get(nid).english_name for nid in path_ids]
                            if current_user.is_authenticated:
                                save_query_history(current_user.id, start_name, end_name, season_id,
                                                   ' → '.join(path_result))
                except Exception as e:
                    error_msg = f"查询异常：{str(e)[:100]}"

    return render_template('path_query.html', nodes=all_nodes, seasons=all_seasons, path_result=path_result,
                           error_msg=error_msg)


# ======================== ✅ 收藏功能（全中文提示） ========================
@app.route('/api/favorite/add', methods=['POST'])
@login_required
def add_favorite():
    with app.app_context():
        char_name = request.form.get('char_name', '').strip()
        if not char_name:
            return jsonify({'code': 0, 'msg': '角色名称不能为空！'})
        char_node = Node.query.filter_by(english_name=char_name).first()
        if not char_node:
            return jsonify({'code': 0, 'msg': '该角色不存在！'})
        exists = Favorite.query.filter_by(user_id=current_user.id, node_id=char_node.node_id).first()
        if exists:
            return jsonify({'code': 0, 'msg': '已添加至收藏！'})
        new_fav = Favorite(user_id=current_user.id, node_id=char_node.node_id, create_time=datetime.now())
        db.session.add(new_fav)
        db.session.commit()
        return jsonify({'code': 1, 'msg': '收藏成功！'})


@app.route('/api/favorite/remove', methods=['POST'])
@login_required
def remove_favorite():
    with app.app_context():
        fav_id = request.form.get('fav_id', '')
        if not fav_id:
            return jsonify({'code': 0, 'msg': '参数错误！'})
        fav = Favorite.query.get(fav_id)
        if not fav or fav.user_id != current_user.id:
            return jsonify({'code': 0, 'msg': '收藏记录不存在！'})
        db.session.delete(fav)
        db.session.commit()
        return jsonify({'code': 1, 'msg': '取消收藏成功！'})


@app.route('/favorites')
@login_required
def show_favorites():
    with app.app_context():
        fav_list = db.session.query(Favorite, Node).join(Node, Favorite.node_id == Node.node_id) \
            .filter(Favorite.user_id == current_user.id).order_by(Favorite.create_time.desc()).all()
    return render_template('user/favorites.html', fav_list=fav_list)


@app.route('/history')
@login_required
def show_history():
    with app.app_context():
        history_list = History.query.filter_by(user_id=current_user.id) \
            .order_by(History.create_time.desc()).limit(50).all()
    return render_template('user/history.html', history_list=history_list)


# ======================== ✅ 启动服务 ========================
if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # 自动创建数据表
    app.run(debug=False, host='0.0.0.0', port=5000, threaded=True)