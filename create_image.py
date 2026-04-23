import pandas as pd
import math
import re
import unicodedata
import os
from playwright.sync_api import sync_playwright

INPUT_RANKING_CSV = 'ranking.csv' # 生成したランキングデータ
INPUT_IMAGE_CSV = 'characters.csv' # 名前と画像URLのマッピング
CHUNK_SIZE = 50  # 何位ごとにファイル分割するか

def generate_html():
    # CSVデータの読み込み
    try:
        ranking_df = pd.read_csv(INPUT_RANKING_CSV)
        image_df = pd.read_csv(INPUT_IMAGE_CSV)
    except FileNotFoundError as e:
        print(f"エラー: {e}")
        print(f"{INPUT_RANKING_CSV} と {INPUT_IMAGE_CSV} が同じディレクトリにあるか確認してください。")
        return

    # 名前をキーにしてランキングデータと画像URLを左結合
    df = pd.merge(ranking_df, image_df[['名前', '画像URL']], on='名前', how='left')

    # 設定された件数（50件）ずつ分割してHTMLを作成
    total_chunks = math.ceil(len(df) / CHUNK_SIZE)

    # CSS
    style = """
    <style>
        body {
            margin: 0;
            padding: 0;
            font-family: sans-serif;
            background-color: #fff;
        }
        .ranking-table {
            width: 1920px;
            border-collapse: collapse;
            table-layout: fixed;
            background-color: #000;
            color: #fff;
        }
        .ranking-row {
            height: 270px;
        }
        .ranking-row td {
            border: none;
            height: 270px;
            box-sizing: border-box;
            position: relative;
            overflow: hidden;
        }
        
        .col-video, .col-res, .col-pixiv, .col-prev {
            text-align: center; 
            vertical-align: middle;
            font-size: 40px;
            font-weight: bold;
        }

        .col-search {
            text-align: center; 
            vertical-align: middle;
            font-size: 32px;
            font-weight: bold;
        }

        .col-rank { 
            text-align: center; 
            vertical-align: middle;
            font-size: 80px;
            font-weight: bold;
        }

        .col-score { 
            text-align: center; 
            vertical-align: middle;
            font-size: 60px;
            font-weight: bold;
        }
        
        /* 各カラムの幅と背景色 */
        .col-rank   { width: 180px; }
        .col-video  { width: 180px; }
        .col-res    { width: 180px; background-color: #151515; }
        .col-pixiv  { width: 180px; }
        .col-search { width: 200px; background-color: #151515; }
        .col-score  { width: 260px; color: #ffeb3b; }
        .col-prev   { width: 260px; background-color: #151515; }
        
        /* 前回順位用の文字色クラス */
        .rank-up   { color: #4dabf7; }
        .rank-down { color: #ff6b6b; }
        .rank-same { color: #ffffff; }
        .rank-new  { color: #ffd43b; }

        /* 名前のカラム */
        .col-name { 
            width: 480px; 
            padding: 0; 
            position: relative; 
            vertical-align: top;
        }
        .name-bg-img {
            width: 100%;
            height: 270px;
            object-fit: cover;
            object-position: center;
            display: block;
        }
        .name-text-container {
            position: absolute;
            bottom: 0;
            left: 0;
            width: 100%;
            padding: 8px 8px;
            box-sizing: border-box;
            background: linear-gradient(transparent, rgba(0,0,0,0.8));
        }
        .name-text {
            margin: 0;
            color: #fff;
            font-weight: bold;
            white-space: nowrap;
            
            /* CSSの clamp() と calc() を使ったサイズ計算 */
            font-size: clamp(10px, calc(440px / var(--len, 10)), 48px);
            
            text-shadow: 
                2px  2px 0 #000,
               -2px -2px 0 #000,
                2px -2px 0 #000,
               -2px  2px 0 #000,
                0px  2px 0 #000,
                0px -2px 0 #000,
                2px  0px 0 #000,
               -2px  0px 0 #000;
        }
    </style>
    """

    # --- キャプチャ用のブラウザを起動 ---
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        
        page = browser.new_page(
            extra_http_headers={"Referer": "https://www.pixiv.net/"}
        )

        for i in range(total_chunks):
            start_idx = i * CHUNK_SIZE
            chunk_df = df.iloc[start_idx:start_idx + CHUNK_SIZE]
            end_idx = start_idx + len(chunk_df)

            html_lines = [
                "<!DOCTYPE html>",
                "<html lang='ja'>",
                "<head>",
                "    <meta charset='utf-8'>",
                f"    <title>Ranking {start_idx+1}-{end_idx}</title>",
                style,
                "</head>",
                "<body>",
                "    <table class='ranking-table'>"
            ]

            for _, row in chunk_df.iterrows():
                try:
                    curr_rank = int(row['順位'])
                except ValueError:
                    curr_rank = 0
                    
                rank = str(row['順位'])
                name = str(row['名前'])
                
                # 全角・半角を考慮した文字数の計算（CSSに渡すための値）
                char_length = 0
                for char in name:
                    if unicodedata.east_asian_width(char) in ('F', 'W', 'A'):
                        char_length += 1
                    else:
                        char_length += 0.7
                
                # 0割り防止
                char_length = max(char_length, 1)

                def format_num(val):
                    try:
                        if pd.isna(val): return ""
                        return f"{int(val):,}"
                    except ValueError:
                        return str(val)

                video = format_num(row['動画'])
                res_count = format_num(row['レス'])
                pixiv = format_num(row['pixiv'])
                search = format_num(row['検索'])
                score = format_num(row['得点'])
                
                prev_val = row.get('前回', row.get('前回順位'))
                prev_str = str(prev_val).strip() if pd.notna(prev_val) else ""
                
                prev_text = ""
                prev_class = ""

                if prev_str.upper() == 'NEW' or prev_str == 'nan' or prev_str == '':
                    prev_text = "NEW"
                    prev_class = "rank-new"
                else:
                    match = re.match(r'^(\d+)', prev_str)
                    if match:
                        prev_rank = int(match.group(1))
                        if prev_rank > curr_rank:
                            diff = prev_rank - curr_rank
                            prev_text = f"{prev_rank} (+{diff})"
                            prev_class = "rank-up"
                        elif prev_rank < curr_rank:
                            diff = curr_rank - prev_rank
                            prev_text = f"{prev_rank} (-{diff})"
                            prev_class = "rank-down"
                        else:
                            prev_text = f"{prev_rank} (-)"
                            prev_class = "rank-same"
                    else:
                        prev_text = "NEW"
                        prev_class = "rank-new"
                
                img_url = row['画像URL']

                html_lines.append("        <tr class='ranking-row'>")
                html_lines.append(f"            <td class='col-rank'>{rank}</td>")
                
                html_lines.append("            <td class='col-name'>")
                if pd.notna(img_url) and str(img_url).strip() != "":
                    html_lines.append(f"                <img class='name-bg-img' src='{img_url}' loading='eager'>")
                html_lines.append("                <div class='name-text-container'>")
                
                # CSS変数 `--len` に文字数を渡す
                html_lines.append(f"                    <div class='name-text' style='--len: {char_length};'>{name}</div>")
                
                html_lines.append("                </div>")
                html_lines.append("            </td>")
                
                html_lines.append(f"            <td class='col-video'>{video}</td>")
                html_lines.append(f"            <td class='col-res'>{res_count}</td>")
                html_lines.append(f"            <td class='col-pixiv'>{pixiv}</td>")
                html_lines.append(f"            <td class='col-search'>{search}</td>")
                html_lines.append(f"            <td class='col-score'>{score}</td>")
                html_lines.append(f"            <td class='col-prev {prev_class}'>{prev_text}</td>")
                
                html_lines.append("        </tr>")
                
            html_lines.append("    </table>")
            html_lines.append("</body>")
            html_lines.append("</html>")
            
            # HTMLファイルの保存
            filename = f"output_{start_idx+1:03d}-{start_idx+CHUNK_SIZE:03d}.html"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write("\n".join(html_lines))
                
            print(f"{filename} を作成しました。")

            # PNG画像のキャプチャと保存
            png_filename = filename.replace('.html', '.png')
            abs_path = os.path.abspath(filename)
            file_url = f"file://{abs_path}"

            print(f"  -> 画像の読み込みを待機して {png_filename} をキャプチャ中...")
            try:
                page.goto(file_url)

                # ページ内のすべての画像が完全に読み込まれるまで最大30秒待機
                page.wait_for_function("""
                    () => {
                        const images = Array.from(document.querySelectorAll('img'));
                        // すべての画像が complete になり、かつ高さが0以上（壊れていない）ことを確認
                        return images.every(img => img.complete && img.naturalHeight > 0);
                    }
                """, timeout=30000)

                # 少しだけ余裕を持たせる（1秒待機）
                page.wait_for_timeout(1000)

                # キャプチャを保存
                page.screenshot(path=png_filename, full_page=True)
                print(f"  -> {png_filename} の保存が完了しました。\n")
                
            except Exception as e:
                print(f"  -> [エラー] キャプチャに失敗しました ({filename}): {e}\n")

        # 全てのループが終わったらブラウザを閉じる
        browser.close()
        print("全ての処理が完了しました。")

if __name__ == "__main__":
    generate_html()