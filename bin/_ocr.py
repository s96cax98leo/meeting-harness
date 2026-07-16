#!/usr/bin/env python3
"""_ocr.py <images_dir> <out_ocr_dir>
用 Apple Vision（ocrmac）對資料夾內所有 .jpg/.png 做繁中+英文 OCR。
單一 process 迭代（避免每張重載框架）。冪等：已存在且非空的 .txt 跳過。
輸出：<out_ocr_dir>/<name>.txt，並回傳 JSON 摘要到 stdout。
"""
import sys, os, json, glob

def main():
    if len(sys.argv) < 3:
        print("usage: _ocr.py <images_dir> <out_ocr_dir>", file=sys.stderr)
        sys.exit(2)
    images_dir, out_dir = sys.argv[1], sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)

    try:
        from ocrmac import ocrmac
    except Exception as e:
        print(json.dumps({"error": f"ocrmac import failed: {e}"}))
        sys.exit(3)

    imgs = sorted(
        glob.glob(os.path.join(images_dir, "*.jpg")) +
        glob.glob(os.path.join(images_dir, "*.jpeg")) +
        glob.glob(os.path.join(images_dir, "*.png"))
    )
    results = []
    for img in imgs:
        base = os.path.splitext(os.path.basename(img))[0]
        out_txt = os.path.join(out_dir, base + ".txt")
        if os.path.exists(out_txt) and os.path.getsize(out_txt) > 0:
            with open(out_txt, encoding="utf-8") as f:
                text = f.read()
            results.append({"image": os.path.basename(img), "chars": len(text), "skipped": True})
            continue
        try:
            anns = ocrmac.OCR(img, language_preference=["zh-Hant", "en-US"]).recognize()
            text = "\n".join(a[0] for a in anns)
        except Exception as e:
            text = ""
            print(f"[ocr] WARN {img}: {e}", file=sys.stderr)
        with open(out_txt, "w", encoding="utf-8") as f:
            f.write(text)
        results.append({"image": os.path.basename(img), "chars": len(text), "skipped": False})
        print(f"[ocr] {os.path.basename(img)} -> {len(text)} chars", file=sys.stderr)

    print(json.dumps({"count": len(results), "results": results}, ensure_ascii=False))

if __name__ == "__main__":
    main()
