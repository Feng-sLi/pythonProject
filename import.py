import pandas as pd
from app import app
from ext import db
from models import Movie, User, Rating
from sqlalchemy import text
import os

MAX_ROWS = 200000

def import_data():
    print(f"🚀 开始导入数据 (限制前 {MAX_ROWS} 条)...")

    try:
        movies_df = pd.read_csv('dataset/movies.csv')
        ratings_df = pd.read_csv('dataset/ratings.csv', nrows=MAX_ROWS)
    except FileNotFoundError as e:
        print(f"❌ 文件未找到: {e}")
        return

    if 'sqlalchemy' not in app.extensions:
        db.init_app(app)

    with app.app_context():
        db.create_all()

        # --- 导入电影 ---
        if Movie.query.first() is None:
            print(f"正在导入 {len(movies_df)} 部电影...")
            movies_list = []
            for _, row in movies_df.iterrows():
                genres = row['genres'] if pd.notna(row['genres']) else "Unknown"
                movie = Movie(
                    id=int(row['movieId']),
                    title=row['title'],
                    genres=genres
                )
                movies_list.append(movie)
            db.session.add_all(movies_list)
            db.session.commit()
            print("✅ 电影导入完成！")
        else:
            print("⚠️ 电影数据已存在，跳过。")

        # --- 导入用户 ---
        unique_user_ids = ratings_df['userId'].unique()
        current_user_count = User.query.count()
        if current_user_count < len(unique_user_ids):
            print(f"正在创建/补全涉及到的 {len(unique_user_ids)} 个用户...")
            existing_ids = {u.id for u in User.query.all()}
            users_list = []
            for uid in unique_user_ids:
                if int(uid) not in existing_ids:
                    user = User(
                        id=int(uid),
                        username=f"User_{uid}",
                        password_hash="123456",
                        email=f"user{uid}@example.com"
                    )
                    users_list.append(user)
            if users_list:
                db.session.add_all(users_list)
                db.session.commit()
            print("✅ 用户导入完成！")
        else:
            print("⚠️ 用户数据已存在，跳过。")
        # --- 更新统计 ---
        print("正在更新电影平均分统计...")
        try:
            sql = """
            UPDATE movie m 
            JOIN (
                SELECT movie_id, AVG(score) as avg_s, COUNT(*) as cnt 
                FROM rating GROUP BY movie_id
            ) r ON m.id = r.movie_id
            SET m.avg_rating = r.avg_s, m.count_rating = r.cnt;
            """
            db.session.execute(text(sql))
            db.session.commit()
            print("✅ 数据初始化全部完成！")
        except Exception as e:
            print(f"统计更新跳过: {e}")

if __name__ == '__main__':
    import_data()