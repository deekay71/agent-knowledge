# Nghiệm thu viewer P2 — 2026-10-18 UTC

P2 hoàn tất local trên `contrib/viewer-phases`, nối tiếp commit P1
`302c7c66cd318c31a4121aee6f306400c04ff3ca`. Tại mốc nghiệm thu này P1/P2 chưa push
hoặc merge main; [bàn giao sau phê duyệt](VIEWER-RELEASE-20261018.md) ghi đợt tiếp theo.
Nhánh public được duyệt vẫn là MVP `contrib/local-graph-viewer` tại
`5b31849749ddde53601d3dab359112707860b50e`; xem [biên nhận MVP](evidence/viewer-p1/mvp-publication.json).

## Phạm vi đã triển khai

- Nhóm xác định theo loại/tag, thu gọn/mở nhóm và truy về cạnh gốc có provenance.
- Lưu/khôi phục tọa độ cùng bộ lọc tại browser theo corpus/origin, không lưu body note.
- Lưới cố định khi bố trí hơn 500 node; vị trí không biểu thị quan hệ ngữ nghĩa.
- So sánh hai commit Git local bằng SHA đầy đủ thuộc ancestry HEAD, tách khỏi graph hiện tại.
- Tự tải lại opt-in 15/30/60 giây, giữ selection/filter/vị trí, không chạy chồng request.
- Xuất JSON/PNG với xác nhận phạm vi; hủy hoặc snapshot thay đổi không tải bản cũ.

Canonical raw/wiki, vault, hooks, auth/Git config và pin project không thay đổi. Không có
server write route, CDN, model/API ngoài hoặc tự upload. Metadata sharing vẫn cần review
nội dung; các nhãn shared/approved không chứng minh dữ liệu không có bí mật.

## Python và review độc lập

[229/229 tests pass](evidence/viewer-p2/python-tests.txt) trong **76,954 giây**:
65 tests viewer/history/HTTP, 10 tests demo và 154 tests nền. Trong 65 tests có 13 kiểm
tra HTTP loopback thật và 19 tests history/corpus mới. Fixtures dùng Git thật nhưng
không phải kiểm chứng kiến thức production hoặc chạy LLM.

Kiểm tra cuối: 78 link tài liệu local và 18 khối lệnh shell hợp lệ; JavaScript syntax
và `git diff --check` pass. Starter `--check` vẫn là 4 node/9 cạnh, không có diagnostic.
Quét 16 file text thay đổi không thấy token/key hoặc đường dẫn home theo các pattern
đã kiểm tra; đây không phải chứng nhận không có mọi loại dữ liệu nhạy cảm.

Review độc lập tìm được hai lỗi đã sửa và có regression: thay `.git` giữa request mà
vẫn giữ file descriptor cũ; header `parent` sai vị trí có thể mở rộng ancestry ngoài
cách Git hiểu commit. Bản sửa kiểm tra lại named directory/HEAD và chỉ nhận parent
liền sau tree. Tree/commit giải nén được kiểm tra kích thước trước khi đọc nội dung.
Reviewer kiểm tra thêm loose/packed, SHA-256, môi trường/config Git không đáng tin,
symlink/alternates và 32 request privacy qua HTTP transport trong bộ nhớ. Các probe
riêng này không cộng thêm vào 229 và không được gọi là TCP/browser tests.

Compare chạy `cat-file` trong object store tạm cô lập, có giới hạn byte/object/time;
không dùng config/hook/remote/alternate của repo gốc. Hai snapshot đều phải hợp lệ;
private revision khiến cả request thất bại. Node lịch sử chỉ trả summary metadata,
không trả body hoặc metadata object đầy đủ. Gitfile của worktree/submodule và repo
vượt giới hạn chưa hỗ trợ compare; vẫn có thể đọc working-tree graph hợp lệ.

## Chrome và ảnh thực tế

[28/28 nhóm browser pass](evidence/viewer-p2/browser-report.json): 10 MVP, 11 P1 và
7 P2. API đọc filesystem/Git thật, không mock response. Kiểm tra hồi quy gồm
Back/Forward, deep link, click/filter lặp, reader/provenance và snapshot lỗi. P2 thử
tọa độ lưu chính xác sau reload, corpus khác không dùng nhầm bản lưu, JSON hỏng được
bỏ qua, grouping không tạo quan hệ giả và canonical counts không bị gộp thành số group.

JSON được tải và đọc lại: 13 note/38 cạnh đủ điều kiện, geometry nhóm UI riêng, không
có node ngoài filter. PNG được kiểm tra signature và kích thước giới hạn. Hủy hai loại
export không tạo download. Synthetic Git history gồm bốn commit; diff hợp lệ HTTP200,
revision private HTTP422, checkout sạch/HEAD không thay đổi.

Auto-refresh chạy timer thật: lượt đầu sau **15,046 giây**, tối đa một request đang chạy;
selection/filter/vị trí đã kéo giữ nguyên. Snapshot invalid xóa nội dung cũ, hủy export
đang xác nhận và tắt opt-in. Hidden pause được thử 16,1 giây qua **visibility adapter**:
không xác nhận native background-tab behavior của hệ điều hành. Clipboard cũng dùng
adapter capture/fallback từ P1; không ghi clipboard của người dùng.

Quan sát **0 request ngoài, 0 page error, 0 vi phạm CSP**. Browser run cuối kết thúc
`2026-10-18T04:34:54.586Z`. Sau lượt này chỉ đổi nhãn nhóm công cụ thành “Dữ liệu & xuất
file”; không đổi logic hoặc selector. Hai ảnh giữ lại đều không hiển thị nhãn cũ:

- [Nhóm tag thu gọn và số note/cạnh canonical](evidence/viewer-p2/p2-groups.png).
- [So sánh hai revision synthetic local](evidence/viewer-p2/p2-git-comparison.png).

Report liệt kê cả ảnh trung gian trong cache của runner; chỉ hai ảnh trên được giữ trong
repo. Đã xem trực tiếp cả hai. Ảnh dùng fixture tổng hợp, không có dữ liệu project riêng.

Lượt browser đầu đạt 27/28: grid mặc định đổi khoảng cách hàng theo label/zoom nên chạy
Sắp lại không cho cùng tọa độ. Đã thay bằng tọa độ cố định theo ID rồi chạy lại toàn bộ
28 nhóm đạt. Review tĩnh cũng đã sửa loading overlay còn hiện khi refresh cùng digest,
và chặn manual refresh chạy chồng compare; không còn blocker cụ thể trong phạm vi review.

## Số đo và giới hạn

Môi trường Apple M4, 16 GiB, macOS arm64, Python 3.14.8, Node 26.11.1,
Chrome 155.0.8059.80, Playwright Core 1.64.1; viewport desktop 1440×1000,
reduced-motion. Lượt cuối đo:

| Fixture | Ready | Layout | Thao tác |
|---|---|---|---|
| 301 node / 1.403 cạnh | 871 ms | 626 ms | Search 19 ms, filter 43 ms. |
| 1.201 node / 5.603 cạnh | 736 ms | 2,4 ms | Fulltext 29 ms, truy nguồn 234 ms. |

P1 trên fixture lớn từng mất 16,37 giây ready; P2 bỏ force layout đầu cho trường hợp
trên 500 node. Đây là các lượt đo riêng trên cùng máy, không phải benchmark kiểm soát
thống kê hoặc SLA. Lưới không thể hiện community/quan hệ suy ra. Chưa đo mọi giới hạn
2.000 note/20.000 cạnh hoặc mọi object store Git hỏng.

Chạy lại bằng [hướng dẫn browser runner](VIEWER-VALIDATION-20261018.md#chạy-lại),
đặt `VIEWER_BROWSER_OUTPUT` để chọn cache kết quả. Runner tạo/dọn corpus, Git history,
server và browser riêng. Bộ Python: `python3 -m unittest discover -s tests -v`.

Chưa test Safari/Firefox/Windows, Obsidian GUI, native clipboard/background-tab behavior
hay agent/LLM production. Không có CI được cấu hình ở mốc publish. Các giới hạn này
mô tả đúng lượt kiểm thử P2; kiểm tra bổ sung sau đó được ghi ở báo cáo bàn giao riêng.

Xem [hướng dẫn và giới hạn](VIEWER.md), [ADR005](ADR-005.md), [P1](VIEWER-P1-VALIDATION-20261018.md).
