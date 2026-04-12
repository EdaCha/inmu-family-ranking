import sys
import os
import time
import csv
import urllib.parse
import requests
import re
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# キャラクター名の入力CSV
INPUT_FILE = "characters.csv"
# 順位比較用過去データ
PAST_DATA_FILE = os.path.join('data', '2024.csv')
# 出力ランキングデータ
OUTPUT_FILE = "ranking7.csv"
# 一件取得毎のウェイト秒。エラーになるようなら伸ばす
SLEEP = 5
# 【要入力】PIXIVのPHPSESSIDクッキー値 誤って公開しないように注意！
PIXIV_COOKIE = ""

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": USER_AGENT}

def get_video_count(keyword):
    """
    ニコニコ動画（API）から動画数を取得
    keyword: "名前1 名前2" のようなスペース区切り文字列
    """
    url = "https://snapshot.search.nicovideo.jp/api/v2/snapshot/video/contents/search"
    
    or_query = keyword.replace("　", " ").replace(" ", " OR ")
    query = f"{or_query}"

    params = {
        "q": query,
        "targets": "tagsExact", # タグ完全一致検索
        "fields": "contentId",
        "_sort": "-viewCounter",
        "_limit": 1
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        count = int(data.get("meta", {}).get("totalCount", 0))
        print(f"動画数[{query}]: {count}")
        return count
    except Exception as e:
        print(f"動画数取得エラー: {e}")
        return 0

def get_res_count(page_name):
    """ニコニコ大百科からレス数を取得（最大3回リトライ）"""
    url = f"https://dic.nicovideo.jp/a/{urllib.parse.quote(page_name)}"
    
    # リトライ回数を3回に設定
    retries = 3
    
    for i in range(retries):
        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # ページが存在しない、または書き込みがない
            page_text = soup.get_text()
            if "まだ記事が書かれていません！" in page_text:
                return 0
            if "まだ掲示板に書き込みがありません" in page_text:
                return 0
                
            # レス番号のタグ（st-bbs_resNo）から最大値を取得
            res_tags = soup.find_all('span', class_='st-bbs_resNo')
            if res_tags:
                res_numbers = [int(tag.get_text(strip=True)) for tag in res_tags]
                count = max(res_numbers)
                print(f"レス数: {count}")
                return count
                
            return 0
            
        except (requests.RequestException, Exception) as e:
            print(f"試行 {i+1}/{retries} 失敗: {e}")
            if i < retries - 1:
                print(f"{SLEEP}秒待機してリトライします...")
                time.sleep(SLEEP)
            else:
                print("リトライ上限に達しました。")
                return 0

def get_image_count(keyword):
    """
    Pixivの内部APIを利用して画像数を取得
    keyword: "名前1 名前2" のようなスペース区切り文字列
    """
    or_query = keyword.replace("　", " ").replace(" ", " OR ")
    encoded_name = urllib.parse.quote(or_query)
    api_url = f"https://www.pixiv.net/ajax/search/artworks/{encoded_name}?word={encoded_name}&s_mode=s_tag_full&type=all"
    
    try:
        # PIXIVはCookieがないと成人向けを含む画像件数を返さないのでヘッダ追加が必要
        pixiv_headers = HEADERS.copy()
        pixiv_headers.update({
            "Referer": "https://www.pixiv.net/",
            "Cookie": f"PHPSESSID={PIXIV_COOKIE}"
        })

        response = requests.get(api_url, headers=pixiv_headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get("error") is False:
            count = int(data["body"]["illustManga"]["total"])
            print(f"画像数: {count}")
            return count
        else:
            print(f"APIエラー: {data.get('message')}")
            return 0
            
    except Exception as e:
        print(f"画像数取得エラー: {e}")
        return 0

def get_search_count_yahoo(keyword):
    """
    Yahoo! JAPAN検索からヒット件数をスクレイピングで取得
    keyword: "名前1 名前2" のようなスペース区切り文字列
    """
    # 全角スペースを半角に統一
    clean_keyword = keyword.replace("　", " ").strip()
    
    # スペースで分割してリスト化し、各要素をダブルクォートで囲む
    parts = filter(None, clean_keyword.split(" "))
    quoted_parts = [f'"{p}"' for p in parts]
    
    # OR で繋ぎ、全体のクエリを構成
    or_query = " OR ".join(quoted_parts)
    query = f'淫夢 ({or_query})'
    # qrw=0 で曖昧検索を無効に
    url = f"https://search.yahoo.co.jp/search?p={urllib.parse.quote(query)}&qrw=0"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True) # ブラウザ表示する場合はfalse
            context = browser.new_context(user_agent=USER_AGENT)
            page = context.new_page()
            
            page.goto(url)
            selector = "div.Hits__item" # ヒット件数は2026/4現在 Hits__item クラスが使われている
            
            try:
                # 画面に件数が出るまで10秒待機
                page.wait_for_selector(selector, timeout=10000)
                text = page.locator(selector).first.inner_text()
                browser.close()
                
                # 数字部分だけを抽出して整数に変換
                match = re.search(r'([0-9,]+)', text)
                if match:
                    count = int(match.group(1).replace(',', ''))
                    print(f"Yahoo検索数[{query}]: {count}")
                    return count
                return 0
                
            except Exception:
                print(f"取得失敗：要素が見つかりません。")
                browser.close()
                return 0
                
    except Exception as e:
        print(f"エラー発生: {e}")
        return 0

def main():
    if not os.path.exists(INPUT_FILE):
        print(f"エラー: {INPUT_FILE} が見つかりません。")
        sys.exit(1)

    # データを格納するリスト
    rows = []

    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)

        try:
            next(reader)
        except StopIteration:
            print(f"エラー: {INPUT_FILE} が空です。")
            return

        for row in reader:
            if not row or not any(field.strip() for field in row):
                continue  # 空行やカンマのみの行をスキップ

            # 1カラム目を「大百科ページ名」として取得
            name = row[0].strip()
            
            # 2カラム目カラムが存在し、中身が空でないならそれが検索用ワード
            # それ以外なら大百科ページ名を検索用ワードとして使用
            if len(row) > 1 and row[1].strip():
                keyword = row[1].strip()
            else:
                keyword = name 

            rows.append((name, keyword))

    results = []
    total_count = len(rows)

    # 前回データ
    past_ranks = {}
    if os.path.exists(PAST_DATA_FILE):
        with open(PAST_DATA_FILE, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row.get('名前')
                rank = row.get('順位')
                if name and rank:
                    try:
                        past_ranks[name.strip()] = int(rank)
                    except ValueError:
                        continue
    else:
        print(f"通知: 過去データ {PAST_DATA_FILE} が見つからないため、すべてNEWになります。")

    print(f"{total_count}件のデータを取得します...")
    
    for i, (name, keyword) in enumerate(rows, 1):
        print(f"[{i}/{total_count}] 取得中: {name}")
        
        video_count = get_video_count(keyword)
        res_count = get_res_count(name)
        image_count = get_image_count(keyword)
        search_count = get_search_count_yahoo(keyword)
        
        time.sleep(SLEEP)
        
        points = video_count + (res_count * 0.5) + image_count + (search_count * 0.001)
        
        results.append({
            "name": name,
            "video": video_count,
            "res": res_count,
            "image": image_count,
            "search": search_count,
            "points": points
        })

    # ポイントの降順でソート
    results.sort(key=lambda x: x['points'], reverse=True)

    # 順位付け
    current_rank = 1
    for i in range(len(results)):
        # 同着処理
        if i > 0 and results[i]['points'] == results[i-1]['points']:
            this_rank = results[i-1]['rank']
        else:
            this_rank = current_rank
        
        results[i]['rank'] = this_rank
        current_rank += 1

        # 前回順位がなければ空欄
        name = results[i]['name']
        results[i]['past_rank'] = past_ranks.get(name, "")

    # CSV出力
    with open(OUTPUT_FILE, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['順位', '名前', '動画', 'レス', 'pixiv', '検索', '得点', '前回'])
        
        for r in results:
            writer.writerow([
                r['rank'], 
                r['name'], 
                r['video'], 
                r['res'], 
                r['image'], 
                r['search'], 
                round(r['points']),
                r['past_rank']
            ])

    print(f"\n処理が完了しました。結果は {OUTPUT_FILE} に保存")


main()