# Nghiệm thu viewer P1 — 2026-10-18 UTC

P1 phát triển local trên `contrib/viewer-phases`, nối tiếp MVP
`5b31849749ddde53601d3dab359112707860b50e`. MVP và README đã được publish lên nhánh
`contrib/local-graph-viewer`; [biên nhận](evidence/viewer-p1/mvp-publication.json)
xác nhận remote SHA, main không đổi và không có CI được cấu hình/chạy. Tại mốc nghiệm
thu này P1 chưa push; [bàn giao sau phê duyệt](VIEWER-RELEASE-20261018.md) ghi đợt tiếp theo.

## Phạm vi

- Tìm chuỗi toàn văn trong note và claim, snippet dạng text; lọc current/archived.
- Lân cận 1–2 bước hai chiều; đường ngắn nhất và truy nguồn theo chiều cạnh tường minh.
- Diagnostics missing source, broken link, orphan page và index drift; không tạo node giả.
- Context có citation, version, nhãn evidence/inference/unknown, mâu thuẫn và giới hạn độ dài.
- Deep link, tab reader và Back/Forward; navigation state không lưu body note.

Canonical raw/wiki, vault, authoring scripts, hooks, Git/auth config và submodule pins
không đổi. Không thêm runtime dependency, CDN, LLM hoặc API ngoài.

## Backend và hồi quy Python

[208/208 tests pass](evidence/viewer-p1/python-tests.txt) trong **63,306 giây**.
Suite gồm 44 tests viewer (33 graph/schema/security và 11 HTTP loopback thật),
10 tests demo generator và 154 tests nền. Đây là unit/integration tests với fixtures,
không phải kiểm chứng kiến thức production hoặc một lượt LLM thực tế.

Review độc lập phát hiện và kiểm tra lại một lỗi privacy: cho index drift thành warning
đã làm body index ngoài schema có thể được trả về. Bản sửa chặn index có frontmatter,
ẩn body/cạnh của index lệch và giữ diagnostic. Các kiểm tra reviewer riêng gồm 33 tests
backend và 16 kiểm tra snapshot/HTTP trong bộ nhớ; chúng không được cộng vào tổng208
và không được gọi là TCP/browser tests.

Review UI đã sửa ý định chọn tất cả tag/quan hệ khi refresh thêm dữ liệu và bổ sung
cảnh báo mâu thuẫn vào context sao chép trước phần nội dung có thể bị cắt.

## Browser QA và ảnh

[21/21 nhóm Chrome thật pass](evidence/viewer-p1/browser-report.json): 10 nhóm MVP và
11 nhóm P1, dữ liệu filesystem/API thật, không mock response. Đã thử query body/claim,
lọc trạng thái, BFS đối chiếu độc lập với cạnh, đường đi đúng chiều/provenance, truy nguồn,
Back/Forward, deep link, click lặp, refresh có tag/quan hệ mới, diagnostics và canary riêng tư.
Quan sát **0 request ngoài, 0 lỗi JavaScript chưa bắt, 0 vi phạm CSP** qua 8 contexts.

Context sao chép được kiểm tra bằng capture `clipboard.writeText` của browser context thử
nghiệm và thử fallback khi adapter từ chối. Đây là kiểm tra payload/luồng UI, **không phải
test ghi clipboard hệ điều hành**; clipboard của người dùng không bị thay thế.

Lượt đầu có bốn lỗi giả định trong test harness (loại cạnh không tồn tại, chọn nhầm kết
quả toàn văn, phần tử bị ẩn); đã sửa harness. Review ảnh sau lượt pass phát hiện dimming
làm phần đầu đường đi khó đọc. Đã sửa và thêm assertion toàn bộ vùng khám phá vẫn rõ,
rồi chạy lại 21 nhóm đạt. Bộ Python không chạy lặp vì thay đổi cuối chỉ ở UI/browser tests.

[Đường đi qua 3 cạnh thật](evidence/viewer-p1/p1-directed-path.png) ·
[Context có citation và mâu thuẫn](evidence/viewer-p1/p1-cited-context.png).

Môi trường Apple M4, 16 GiB, macOS arm64, Python 3.14.8, Node 26.11.1,
Chrome 155.0.8059.80, Playwright Core 1.64.1; desktop 1440×1000, reduced-motion.
Lần cuối: 301 node/1.403 cạnh ready **1,17 giây**; 1.201 node/5.603 cạnh ready **16,37 giây**,
trong đó layout 15,55 giây. Tìm toàn văn 159 ms, truy nguồn 228 ms trên fixture lớn,
bao gồm overhead điều khiển browser. Đây là số đo một lần, không phải SLA; layout ban
đầu của graph lớn còn chậm. P2 sẽ thay cách bố trí ban đầu cho trường hợp lớn này.

Chạy lại browser suite bằng dependency test riêng như [hướng dẫn MVP](VIEWER-VALIDATION-20261018.md#chạy-lại).
Runner tự tạo/dọn fixtures và server local. Kết quả mặc định ở `.cache/viewer-browser/`;
có thể đặt `VIEWER_BROWSER_OUTPUT` tới thư mục evidence thử nghiệm khác.

## Giới hạn

Diagnostics chỉ kiểm tra cấu trúc. Metadata shared/approved không chứng minh quyền chia sẻ
hoặc tính đúng của nội dung. Snapshot thiếu nguồn vẫn hiển thị với cảnh báo; private,
unsafe hoặc malformed input bị chặn toàn bộ. Graph chỉ trích các liên kết được hỗ trợ,
không bao phủ toàn bộ cú pháp CommonMark hay mọi mâu thuẫn ngữ nghĩa.

Context có giới hạn; việc sao chép không phải tác vụ ingest. Trình duyệt không cho
clipboard thì có bản xem trước để sao chép thủ công. Lịch sử filter/query là state của
tab; deep link không lưu body hoặc toàn bộ preference. Không có test LLM/production,
Obsidian GUI, Safari/Firefox/Windows hay chứng nhận hiệu năng cho mọi giới hạn backend.

Xem [hướng dẫn](VIEWER.md), [ADR004](ADR-004.md) và [báo cáo MVP](VIEWER-VALIDATION-20261018.md).
