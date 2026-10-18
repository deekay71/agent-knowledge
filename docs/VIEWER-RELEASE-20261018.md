# Bàn giao viewer MVP / P1 / P2 — 2026-10-18 UTC

Phạm vi đã duyệt gồm MVP, P1 và P2; không có phase tiếp theo được tự thêm. Rà soát code,
tests và các báo cáo trước không thấy tính năng đã hứa nào còn thiếu trong ba giai đoạn.
Đợt hoàn thiện này bổ sung bằng chứng browser, sửa mô tả timezone và ghi rõ giới hạn
bộ nhớ Git. Không đổi logic sản phẩm hoặc nội dung canonical.

## Checklist tính năng

| Phạm vi | Trạng thái và bằng chứng | Giới hạn còn lại |
|---|---|---|
| MVP: graph, filter loại/topic, reader, provenance, refresh thủ công | Đã triển khai; click canvas, đọc note/cạnh, filter và lỗi snapshot có Chrome QA. | Chỉ quan hệ tường minh; không chứng minh claim đúng. |
| P1: fulltext, lân cận 1–2 hop, đường đi có chiều, truy nguồn | Đã triển khai; BFS đối chiếu với cạnh thật, tìm body/claim và lọc phiên bản/trạng thái có tests. | Tìm chuỗi, không semantic search; vị trí không suy ra quan hệ. |
| P1: diagnostics, context có citation, deep link, Back/Forward | Đã triển khai; kiểm tra lỗi nguồn/index/link và lịch sử điều hướng. Clipboard native có bằng chứng bổ sung bên dưới. | Chẩn đoán cấu trúc; context giới hạn 16.000 ký tự. |
| P2: nhóm loại/tag, thu gọn/mở nhóm, lưu/khôi phục layout | Đã triển khai; provenance gốc, số canonical, tọa độ sau reload và storage lỗi được kiểm tra. | Nhóm UI dẫn xuất; storage theo corpus/origin, không đồng bộ giữa máy. |
| P2: so sánh revision Git | Đã triển khai; Git history thật, loose/packed, private revision bị chặn và checkout không đổi. | Hai SHA đầy đủ trong ancestry HEAD; chỉ `.git/` bên trong root; có ngưỡng tài nguyên. |
| P2: auto-refresh opt-in, giữ selection/filter/vị trí | Đã triển khai; timer thật 15 giây, không chồng request, xóa stale snapshot khi lỗi. | Native hidden-tab chưa được chứng minh trong môi trường này; branch tạm dừng đã test bằng adapter. |
| P2: xuất JSON/PNG có xác nhận | Đã triển khai; tải file thật, kiểm tra phạm vi/nội dung/kích thước, Hủy không tải. | JSON gồm thành viên nhóm thu gọn còn đủ filter; kiểm tra quyền trước khi chia sẻ. |
| Giới hạn đọc, dữ liệu riêng, nguồn không đáng tin | HTTP/path/symlink/private-history regression, CSP và request ngoài có kiểm tra. | Metadata approved không phải kiểm chứng quyền hoặc bộ phát hiện bí mật. |

## Kiểm thử đợt bàn giao

[Python: 229/229 pass](evidence/viewer-release/python-tests.txt), **72,708 giây**.
Đây là lượt chạy lại toàn bộ suite, gồm workflow wiki/submodule/hooks/vault và
viewer/history/HTTP. Fixture synthetic và Git local không phải test LLM production.

[Báo cáo hồi quy Chrome](evidence/viewer-release/browser-report.json): **28/28 pass**,
kết thúc `2026-10-18T04:47:55.377Z`, với filesystem, server loopback và Git thật;
không mock response API. Qua 12 browser contexts: 0 request ngoài, 0 page error,
0 vi phạm CSP. Fixture 1.201 node/5.603 cạnh ready 924 ms, fulltext 59 ms, truy nguồn
287 ms; timer refresh thật 15,052 giây. Đây là số đo một lượt, không phải SLA.
Kết quả đợt này bổ sung cho các báo cáo lịch sử
[MVP](VIEWER-VALIDATION-20261018.md), [P1](VIEWER-P1-VALIDATION-20261018.md) và
[P2](VIEWER-P2-VALIDATION-20261018.md), không thay đổi cách phân loại test cũ.

[Browser native bổ sung](evidence/viewer-release/native-browser-report.json) có
**2 pass, 0 fail, 1 unsupported** trên Chrome 155.0.8059.80:

- Nút sao chép trong UI ghi qua `navigator.clipboard.writeText` thật; đọc lại bằng
  `readText` thật khớp 2.854 ký tự, gồm fixture, hai version và đường dẫn nguồn.
  Không override navigator/method. Test chạy trong Chrome headless riêng, dùng
  clipboard của browser; không đọc hoặc sửa clipboard hệ điều hành của người dùng.
- Không page error hoặc request ngoài trong lượt native.
- Hai thao tác chuyển target/tab thật trong cùng cửa sổ vẫn trả `visibilityState:
  visible`. Vì vậy test native hidden-tab là **unsupported**, không gọi là pass.
  Không sửa `document.hidden`/timer để biến nó thành bằng chứng native.

Chrome headless có clipboard độc lập nền tảng theo
[mã nguồn Chromium](https://chromium.googlesource.com/chromium/src/+/main/chrome/browser/headless/chrome_browser_main_extra_parts_headless.cc).
Kết quả trên chứng minh API browser hoạt động; không chứng minh tích hợp clipboard
desktop hoặc hành vi tab ẩn trên mọi máy. Lần chạy setup đầu cần thêm cờ automation
cho kiểm tra launch command; sửa test harness, không sửa sản phẩm.

Chạy lại native proof sau khi chuẩn bị dependency test theo
[hướng dẫn browser](VIEWER-VALIDATION-20261018.md#chạy-lại):

```sh
PLAYWRIGHT_MODULE="$PWD/.cache/viewer-test-deps/node_modules/playwright-core" node tests/viewer_native_browser.cjs
```

Môi trường: macOS arm64, Apple M4/16 GiB, Python 3.14.8, Node 26.11.1,
Chrome 155.0.8059.80, Playwright Core 1.64.1. Chưa chạy Safari/Firefox/Windows,
Obsidian GUI hoặc agent/LLM production. Obsidian GUI không chặn bàn giao viewer.

## Review và ảnh bàn giao

Review độc lập không thấy blocker cụ thể. Đã sửa mô tả giờ: API ISO là UTC, UI dùng
múi giờ trình duyệt. Đã bổ sung giới hạn packed delta: preflight giới hạn object được
yêu cầu/response, không đặt trần RSS của Git. Không mô tả compare như memory sandbox
hoặc deadline cứng cho mọi hoạt động hệ điều hành. Xem [giới hạn đầy đủ](VIEWER.md).

Preflight cuối: 104 link tài liệu local và 18 khối shell hợp lệ; syntax JavaScript,
`git diff --check` và starter `--check` pass (4 node/9 cạnh, 0 diagnostic). Quét 42
phiên bản file text thuộc hai commit P1/P2 cùng thay đổi bàn giao không thấy token,
private key, credential nhúng hoặc đường dẫn home theo các pattern đã kiểm tra.
Review riêng cũng xem bốn ảnh PNG synthetic. Đây không phải chứng nhận phát hiện
mọi bí mật. Raw/wiki/vault/hooks và con trỏ project không đổi.

- [Ảnh P1: đường đi có provenance](evidence/viewer-p1/p1-directed-path.png).
- [Ảnh P2: nhóm thu gọn](evidence/viewer-p2/p2-groups.png).
- [Ảnh P2: so sánh Git](evidence/viewer-p2/p2-git-comparison.png).

Các ảnh là screenshot Chrome với dữ liệu synthetic, không phải mockup hoặc kiến thức
production. Thử lại lưu hai ảnh P1/P2 vào Library theo luồng được hỗ trợ vẫn thất bại
ở kết nối TLS, trước khi upload. Không tắt kiểm tra chứng chỉ hoặc chuyển sang luồng
bypass; file trong repo là bản bàn giao truy cập được sau push.

## Publication và chạy thử

Người dùng đã duyệt normal push P1/P2 và sửa hoàn thiện trong phạm vi viewer vào
public `deekay71/agent-knowledge`, nhánh `contrib/local-graph-viewer`. Không force push,
merge main, đổi visibility/quyền hoặc cập nhật project thật. Các commit tính năng:

| Giai đoạn | SHA |
|---|---|
| MVP | `5b31849749ddde53601d3dab359112707860b50e` |
| P1 | `302c7c66cd318c31a4121aee6f306400c04ff3ca` |
| P2 | `4e439737bd3fb83ed4a594654bea1af899dbdaf2` |

Commit bàn giao kế tiếp chứa tài liệu, test native và evidence. SHA remote cuối/CI
được kiểm tra sau khi push và báo trong phản hồi bàn giao; không coi commit local là
đã publish. Main baseline là `67e8bfb22a3281092c0e4bded0a3b702b279b486`.

```sh
git clone --branch contrib/local-graph-viewer https://github.com/deekay71/agent-knowledge.git
cd agent-knowledge
python3 scripts/viewer.py --check
python3 scripts/viewer.py
```

Mở `http://127.0.0.1:8765/`; Ctrl+C để dừng. Không cần npm hoặc API key để dùng viewer.
Xem [hướng dẫn chi tiết](VIEWER.md), [README](../README.md) và [publication policy](PUBLISHING.md).
