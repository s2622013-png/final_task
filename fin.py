import sqlite3
import time
import requests
from bs4 import BeautifulSoup
import json
import re

url = 'https://github.com/orgs/google/repositories'
response = requests.get(url)

# --- ここから続きのコード ---

# User-Agentを設定してブロックを回避（2ページ目以降用）
headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# 1. SQLiteデータベースの準備
conn = sqlite3.connect('google_repos.db')
cur = conn.cursor()

cur.execute('''
CREATE TABLE IF NOT EXISTS repositories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    language TEXT,
    stars INTEGER
)
''')
cur.execute('DELETE FROM repositories')

# 2. 全ページ分のスクレイピング処理
page = 1
while True:
    if page > 1:
        time.sleep(1)  # サーバー負荷軽減のため1秒待機
        target_url = f'{url}?page={page}'
        response = requests.get(target_url, headers=headers)
    else:
        time.sleep(1)

    soup = BeautifulSoup(response.text, 'html.parser')
    repos_in_page = []

    # パターンA: GitHubの最新React/JSON埋め込みデータから取得（最も確実）
    script_tag = soup.find('script', {'type': 'application/json', 'data-target': 'react-app.embeddedData'})
    if script_tag and script_tag.string:
        try:
            data = json.loads(script_tag.string)
            # payload内のrepositoriesリストを探索
            payload = data.get('payload', {})
            repo_list = payload.get('repositories', [])
            for r in repo_list:
                name = r.get('name', 'Unknown')
                lang_obj = r.get('primaryLanguage')
                language = lang_obj.get('name') if isinstance(lang_obj, dict) and lang_obj.get('name') else 'None'
                stars = int(r.get('starsCount', 0))
                repos_in_page.append((name, language, stars))
        except Exception:
            pass

    # パターンB: 従来のHTMLタグ構造からのフォールバック（クラス名に依存しない検索）
    if not repos_in_page:
        # /google/リポジトリ名 へのリンクを起点に親要素をたどる
        repo_links = soup.find_all('a', href=re.compile(r'^/google/[^/]+$'))
        seen_names = set()
        for link in repo_links:
            name = link.text.strip()
            # ナビゲーション等の不要なリンクを除外
            if not name or name in seen_names or name in ['repositories', 'people', 'projects', 'packages', 'teams']:
                continue
            
            # 親のリスト要素(li)を探す
            parent_li = link.find_parent('li')
            if not parent_li:
                continue

            seen_names.add(name)

            # 言語の取得
            lang_tag = parent_li.find('span', attrs={'itemprop': 'programmingLanguage'})
            if not lang_tag:
                # 言語アイコン(丸い色付きspan)の隣のテキストを探す
                color_dot = parent_li.find('span', style=re.compile(r'background-color'))
                if color_dot and color_dot.parent:
                    language = color_dot.parent.text.strip()
                else:
                    language = 'None'
            else:
                language = lang_tag.text.strip()

            # スター数の取得
            star_tag = parent_li.find('a', href=re.compile(r'/stargazers$'))
            if star_tag:
                star_text = star_tag.text.strip().replace(',', '')
                if 'k' in star_text.lower():
                    stars = int(float(star_text.lower().replace('k', '')) * 1000)
                elif 'm' in star_text.lower():
                    stars = int(float(star_text.lower().replace('m', '')) * 1000000)
                else:
                    stars = int(star_text) if star_text.isdigit() else 0
            else:
                stars = 0

            repos_in_page.append((name, language, stars))

    # 1件も取得できなければ最終ページ到達とみなして終了
    if not repos_in_page:
        break

    # データベースへ挿入
    for repo_name, language, stars in repos_in_page:
        cur.execute(
            'INSERT INTO repositories (name, language, stars) VALUES (?, ?, ?)',
            (repo_name, language, stars)
        )

    print(f'{page}ページ目の取得が完了しました（{len(repos_in_page)}件）')
    page += 1

conn.commit()

# 3. 保存したデータをSELECT文で表示
print('\n--- データベースに保存されたリポジトリ一覧 ---')
cur.execute('SELECT id, name, language, stars FROM repositories')
rows = cur.fetchall()

for row in rows:
    print(f'ID: {row[0]} | リポジトリ名: {row[1]} | 言語: {row[2]} | スター数: {row[3]}')

print(f'\n合計取得件数: {len(rows)}件')

conn.close()