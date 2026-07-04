from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from config import Config
from ext import db
from models import User, Movie, Rating, Collection  # 导入收藏模型
from services.recommendation import RecommendationService
from datetime import datetime

app = Flask(__name__)
app.config.from_object(Config)

# 初始化数据库和登录管理器
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # 未登录跳转登录页

# 推荐服务实例
rec_service = RecommendationService()


# 用户加载回调
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ---------------------- 首页路由 ----------------------
@app.route('/')
def index():
    # 获取用户推荐（仅登录后）
    user_recs = []
    if current_user.is_authenticated:
        user_recs = rec_service.user_based_cf(current_user.id)

    # 获取热门电影（按评分人数排序，取前8部）
    popular_movies = Movie.query.order_by(Movie.count_rating.desc()).limit(8).all()

    return render_template(
        'index.html',
        user_recs=user_recs,
        popular_movies=popular_movies
    )


# ---------------------- 电影详情路由 ----------------------
@app.route('/movie/<int:movie_id>')
def movie_detail(movie_id):
    movie = Movie.query.get_or_404(movie_id)
    rating_count = Rating.query.filter_by(movie_id=movie_id).count()
    item_cf_recs = rec_service.item_based_cf(movie_id)
    content_recs = rec_service.recommend_by_genre(movie_id=movie_id)

    # 当前用户的评分和收藏状态
    user_score = None
    is_collected = False
    if current_user.is_authenticated:
        user_rating = Rating.query.filter_by(user_id=current_user.id, movie_id=movie_id).first()
        if user_rating:
            user_score = user_rating.score
        user_collection = Collection.query.filter_by(user_id=current_user.id, movie_id=movie_id).first()
        if user_collection:
            is_collected = True

    return render_template(
        'detail.html',
        movie=movie,
        rating_count=rating_count,
        item_cf_recs=item_cf_recs,
        content_recs=content_recs,
        user_score=user_score,
        is_collected=is_collected
    )


# ---------------------- 打分路由（修复时间赋值，确保提交才生成记录） ----------------------
@app.route('/rate/<int:movie_id>', methods=['POST'])
@login_required
def rate_movie(movie_id):
    score = request.form.get('score')
    if not score:
        flash('请选择评分！', 'warning')
        return redirect(url_for('movie_detail', movie_id=movie_id))

    try:
        score = float(score)
        # 评分范围校验
        if score < 1 or score > 5:
            flash('评分必须在1-5分之间！', 'warning')
            return redirect(url_for('movie_detail', movie_id=movie_id))

        # 查询用户是否已评分
        existing_rating = Rating.query.filter_by(user_id=current_user.id, movie_id=movie_id).first()
        # 获取当前时间的有效Unix时间戳
        current_timestamp = int(datetime.utcnow().timestamp())

        if existing_rating:
            # 更新已有评分，同步更新时间
            existing_rating.score = score
            existing_rating.timestamp = current_timestamp
            flash('评分更新成功！', 'success')
        else:
            # 新增评分，赋值有效时间戳（仅提交后生成记录）
            new_rating = Rating(
                user_id=current_user.id,
                movie_id=movie_id,
                score=score,
                timestamp=current_timestamp
            )
            db.session.add(new_rating)
            flash('评分提交成功！', 'success')

        # 更新电影评分统计
        update_rating_stats(movie_id)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f'评分失败：{str(e)}', 'danger')

    return redirect(url_for('movie_detail', movie_id=movie_id))


# ---------------------- 收藏/取消收藏路由 ----------------------
@app.route('/collect/<int:movie_id>', methods=['POST'])
@login_required
def collect_movie(movie_id):
    try:
        # 检查收藏状态
        existing_collection = Collection.query.filter_by(user_id=current_user.id, movie_id=movie_id).first()
        if existing_collection:
            # 取消收藏
            db.session.delete(existing_collection)
            flash('取消收藏成功！', 'success')
        else:
            # 新增收藏
            new_collection = Collection(
                user_id=current_user.id,
                movie_id=movie_id
            )
            db.session.add(new_collection)
            flash('收藏成功！', 'success')

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f'收藏操作失败：{str(e)}', 'danger')

    return redirect(url_for('movie_detail', movie_id=movie_id))


# ---------------------- 辅助函数：更新电影评分统计 ----------------------
def update_rating_stats(movie_id):
    ratings = Rating.query.filter_by(movie_id=movie_id).all()
    if not ratings:
        avg_score = 0.0
        rating_count = 0
    else:
        total_score = sum([r.score for r in ratings])
        avg_score = round(total_score / len(ratings), 1)  # 保留1位小数
        rating_count = len(ratings)

    # 同步更新movie表
    movie = Movie.query.get(movie_id)
    movie.avg_rating = avg_score
    movie.count_rating = rating_count
    return


# ---------------------- 登录路由 ----------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and password == '123456':
            login_user(user)
            flash('登录成功！', 'success')
            return redirect(url_for('index'))
        else:
            flash('用户名或密码错误！', 'danger')
    return render_template('login.html')


# ---------------------- 登出路由 ----------------------
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('退出登录成功！', 'success')
    return redirect(url_for('index'))


# ---------------------- 我的收藏列表路由 ----------------------
@app.route('/my-collections')
@login_required
def my_collections():
    # 查询当前用户收藏（按收藏时间倒序）
    user_collections = Collection.query.filter_by(user_id=current_user.id).order_by(Collection.create_time.desc()).all()
    # 关联电影信息
    collected_movies = []
    for coll in user_collections:
        movie = Movie.query.get(coll.movie_id)
        if movie:
            collected_movies.append({
                'collection_time': coll.create_time,
                'movie': movie
            })
    return render_template('my_collections.html', collected_movies=collected_movies)


# ---------------------- 我的打分历史路由 ----------------------
@app.route('/my-ratings')
@login_required
def my_ratings():
    # 查询当前用户打分记录（按打分时间倒序）
    user_ratings = Rating.query.filter_by(user_id=current_user.id).order_by(Rating.timestamp.desc()).all()
    # 关联电影信息
    rated_movies = []
    for rating in user_ratings:
        movie = Movie.query.get(rating.movie_id)
        if movie:
            # 转换时间戳为可读时间
            rating_time = None
            if rating.timestamp and rating.timestamp > 0:
                rating_time = datetime.fromtimestamp(rating.timestamp)
            rated_movies.append({
                'rating_score': rating.score,
                'rating_time': rating_time,
                'movie': movie
            })
    return render_template('my_ratings.html', rated_movies=rated_movies)


# ---------------------- 程序入口 ----------------------
if __name__ == '__main__':
    app.run(debug=True)