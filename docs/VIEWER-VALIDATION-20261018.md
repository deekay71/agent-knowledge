# Nghiệm thu viewer local — 2026-10-18 UTC

MVP viewer được triển khai trên `contrib/local-graph-viewer`, kế thừa nguyên commit docs
`c89940b0b42f0773db994f3f6e4ae0c1f978569e`. Chưa push/publish viewer hoặc commit docs đó.
Các thay đổi gồm server/graph builder, giao diện, thư viện vendored, demo/test và tài liệu;
không thay canonical raw/wiki, vault, hook policy hoặc cấu hình Git/auth của repo làm việc.

## Implemented và tested

- Graph nền tối: zoom, pan, drag, chọn node/cạnh, fit/reset và highlight láng giềng qua
  **cạnh đang hiện**. Tìm title/ID bằng bàn phím; lọc loại + tag, số đếm và select-all.
- Reader Markdown, nguồn/version, evidence/inference/unknown, backlinks và outgoing links.
  Cạnh có loại và vị trí khai báo body/metadata. Không suy ra cạnh hoặc tự phân community.
- Refresh thủ công đọc snapshot mới; hiển thị HEAD khi metadata nằm trong root, mtime index
  và thời gian load. Snapshot lỗi xóa dữ liệu và số đếm cũ. HEAD không chứng nhận working tree sạch.
- Server chỉ bind loopback, đọc confined regular files; chặn symlink, private scope,
  traversal, nguồn thiếu/không hợp lệ, Host/Origin sai và phương thức ghi. Các lỗi trả
  thông báo không kèm nội dung nguồn/path tuyệt đối. Giới hạn tài nguyên có regression tests.
- Markdown tắt HTML, qua sanitizer; metadata là text, không tải ảnh/nguồn ngoài tự động.
  Link HTTP(S) cần thao tác click, có `noopener noreferrer`/`no-referrer`.

[197 unit/integration tests Python pass](evidence/viewer/python-tests.txt) trong **65,797 giây**:
154 tests hiện có, 33 tests viewer và 10 tests generator. Bao gồm HTTP loopback thật,
Git/submodule fixtures, nguồn private/symlink, metadata giả nhãn verified, link có code label,
revision confined, API chỉ đọc và snapshot validation.

[10 nhóm browser integration tests pass](evidence/viewer/browser-report.json) với Chrome thật,
API thật và dữ liệu thử ở filesystem tạm; **không mock API response**. Đã thử click canvas
node/cạnh, kéo node/nền, zoom/fit/reset, search/filter, provenance/backlinks, XSS/images,
refresh lỗi và phục hồi, và viewport 390×844 không tràn ngang. Đã quan sát **0 request ngoài,
0 uncaught page error, 0 CSP violation** trong các browser contexts được test. Không coi
các quan sát này là bằng chứng bao phủ mọi nội dung hoặc mọi đường tấn công.

Review độc lập backend/frontend đã tái hiện và kiểm tra lại các lỗi được sửa: link có code
trong nhãn bị bỏ sót, metadata raw làm sai badge/version, đọc Git config ngoài root,
lookup link tăng theo bình phương, highlight qua cạnh đã ẩn và summary cũ sau refresh lỗi.
CSP được giữ chặt bằng stylesheet local có ID Cytoscape nhận diện, không mở inline script/style element.

Kiểm tra staged hook đạt; các bundle vendored khớp SHA-256 trong manifest. Kiểm tra
whitespace của diff có một ngoại lệ: dấu cách cuối dòng 38 của license MPL upstream
được giữ nguyên cùng văn bản license. Các file còn lại không có lỗi whitespace.

## Ảnh từ browser thật

[Starter canonical: 4 node / 9 cạnh](evidence/viewer/canonical.png) ·
[Demo toàn bộ: 49 node / 227 cạnh](evidence/viewer/demo-49.png) ·
[Lọc một topic và đọc bài](evidence/viewer/demo-topic-focus.png) ·
[Evidence và mâu thuẫn còn mở](evidence/viewer/demo-comparison-detail.png).

Starter và demo đều là fixture synthetic. Graph không thêm node để làm hình dày hơn.
Demo lớn ở thư mục riêng, không trở thành tri thức production của shared wiki.

## Performance quan sát được

Môi trường: Apple M4, 10 logical CPUs, 16 GiB RAM, macOS/Darwin 25.2.0 arm64;
Python 3.14.8, Node 26.11.1, Playwright Core 1.64.1, Chrome 155.0.8059.80.
Browser headless, viewport desktop 1440×1000, local assets, reduced-motion, không mạng ngoài.

| Dataset | Node / cạnh | Build backend median | Browser graph ready | Layout |
|---|---:|---:|---:|---:|
| Starter canonical | 4 / 9 | 0,56 ms | 184 ms | 5,9 ms |
| Synthetic 8 topics | 49 / 227 | 5,06 ms | 173 ms | 39,1 ms |
| Synthetic 50 topics | 301 / 1.403 | 30,30 ms | 1.139 ms | 856,1 ms |

Backend: [5 lần build liên tiếp mỗi dataset](evidence/viewer/backend-benchmark.json), filesystem
cache đã ấm; gồm đọc hai lượt, validation và graph build, không gồm HTTP/layout. Payload dataset
301 node khoảng 820 KB JSON. Browser: số đo **một lần cuối**, từ navigation đến ready; layout
đo qua event Cytoscape, nên các cột không cộng trực tiếp. Dataset 301 node: search **14,6 ms**,
filter **40,4 ms**, gồm overhead điều khiển/wait của Playwright. Không phải cold-start benchmark,
throughput test, SLA hoặc kiểm chứng hiệu năng tại giới hạn 2.000 node/20.000 cạnh.

## Chạy lại

Runtime và unit tests không cần cài npm:

```sh
python3 scripts/viewer.py --check
python3 -m unittest discover -s tests -v
python3 scripts/viewer_demo.py --output ../viewer-demo --topics 8
python3 scripts/viewer.py --root ../viewer-demo --port 8766
```

Browser tests cần Node, `playwright-core@1.64.1` và Chrome riêng. Máy test đã dùng package
Playwright từ registry npm chính thức, xác minh integrity trước khi giải nén, không chạy
install scripts. Có thể chuẩn bị dependency test vào cache riêng bằng lệnh tương đương:

```sh
npm install --prefix .cache/viewer-test-deps --cache .cache/npm --registry=https://registry.npmjs.org --ignore-scripts --no-audit --no-fund playwright-core@1.64.1
PLAYWRIGHT_MODULE="$PWD/.cache/viewer-test-deps/node_modules/playwright-core" node tests/viewer_browser.cjs
```

Trên Mac, test mặc định dùng Chrome trong `/Applications/Google Chrome.app`; có thể đặt
`CHROME_PATH` tới executable Chrome của máy. Lần chạy được ghi nhận dùng module đã giải nén
trong cache, không chạy lệnh npm install minh họa ở trên. Test tạo profile và fixtures riêng,
đọc starter canonical, lưu report/ảnh vào `.cache/viewer-browser`, rồi dừng server test.
Cần quyền chạy subprocess Chrome và bind loopback. Không dùng profile đăng nhập của người dùng.

## Chưa tested / deferred

- Chưa chạy Safari/Firefox, Windows, screen reader hoặc kiểm thử tải dài hạn.
- Revision là `null` cho gitfile submodule/worktree trỏ ngoài root; giới hạn có chủ đích.
- Chưa có CI run, public deployment, review ngữ nghĩa bằng LLM hoặc dữ liệu production.
- Full-text/hops/path/context-copy/diagnostics, clustering/Git-diff/auto-refresh/viewer-export
  thuộc scope sau. Export vault hiện có vẫn hoạt động độc lập.
- Đây là local viewer, không phải server nhiều người dùng; metadata shared/approved không
  thay kiểm tra nội dung có quyền chia sẻ. Xem [hướng dẫn](VIEWER.md) và [ADR](ADR-003.md).
