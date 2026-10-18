# Viewer graph local

Viewer mở graph và nội dung canonical ngay trong trình duyệt, chỉ đọc qua HTTP tại
`127.0.0.1`. Không cần Obsidian, Node.js, npm, API key hoặc dịch vụ LLM để chạy.
Python dùng thư viện chuẩn; các thư viện giao diện đã có sẵn trong `viewer/vendor/`.
Đây là phần triển khai local trên nhánh đóng góp; không tự publish hoặc bật server nền.

## Chạy và dừng

Từ root clone có mã viewer:

```sh
python3 scripts/viewer.py --check
python3 scripts/viewer.py
```

`--check` đọc và kiểm tra snapshot, in JSON gồm số node/cạnh, fingerprint, revision và
cảnh báo; không mở HTTP hoặc tạo file export. Lệnh thứ hai in URL
`http://127.0.0.1:8765/`. Mở đúng URL đó; dùng **Ctrl+C** trong terminal để dừng server.
Không dùng `localhost`: kiểm tra Host của server yêu cầu đúng `127.0.0.1:PORT`.

Cú pháp đầy đủ:

```text
python3 scripts/viewer.py [--root ROOT] [--port PORT] [--check]
```

Root mặc định là repo chứa `scripts/viewer.py`, không phải cwd của shell. `--port` mặc
định 8765, nhận 0–65535; 0 yêu cầu hệ điều hành chọn cổng trống, xem URL thực tế in ra.
Không có option đổi host hoặc `--export`. Mã thoát là 0 khi check thành công/dừng bằng
Ctrl+C, 2 khi sai tham số, không đọc được snapshot hoặc không mở được server.

Đọc một wiki khác hoặc checkout submodule đã pin bằng runtime của clone hiện tại:

```sh
python3 scripts/viewer.py --root /absolute/project/knowledge/shared --port 8766
```

Root phải chứa canonical `raw/` và `wiki/`; không trỏ tới `vault/`. UI/assets vẫn lấy từ
clone chứa script. Viewer không cần nhánh `contrib/...` vì không ghi knowledge; dùng được
với main hoặc submodule detached. Revision chỉ đọc được khi `.git/` là thư mục nằm trong
root. Worktree/submodule thường dùng file `.git` trỏ ra ngoài root, nên revision của chúng
hiển thị không có dữ liệu; viewer vẫn đọc canonical bình thường. Có thể kiểm tra pin bằng
Git riêng khi cần. Việc đọc canonical không yêu cầu tạo Git repo mới.

## Đọc graph

- Tìm node theo title hoặc ID/đường dẫn, không phân biệt hoa thường/dấu tiếng Việt.
  Dùng ↑/↓ và Enter để chọn kết quả, Escape để xóa tìm kiếm. Chưa có tìm toàn văn.
- Lọc theo loại node và topic/tag: node phải khớp một loại đã chọn và ít nhất một tag
  đã chọn. Nhóm **Không có tag** dành cho note không gắn tag. Filter quan hệ chỉ ẩn
  cạnh, không tự ẩn node. Số cạnh/node ở header là đang hiện/tổng; số cạnh/tag trong
  checkbox đếm toàn snapshot. Filter chỉ điều khiển hiển thị, không phân quyền dữ liệu.
- Chọn node để đọc nội dung, metadata, các cạnh đi ra và backlink. Nhãn fixture,
  status, phiên bản và evidence/inference/unknown vẫn phải được đọc cùng claim.
- Chọn cạnh để xem loại quan hệ và nơi khai báo, ví dụ `metadata.sources` hoặc
  `metadata.claims[0].sources`. Cạnh từ link Markdown có provenance `body`, chưa có
  số dòng hoặc vị trí heading chính xác.
- Tab **Liên kết** liệt kê cạnh đi ra/backlink của toàn snapshot, kể cả cạnh bị ẩn
  bởi filter. Chọn tham chiếu để chuyển sang note hoặc xem chi tiết cạnh.
- Dùng **Tải lại dữ liệu** sau khi sửa canonical để nạp snapshot mới. Nếu load thất
  bại, graph/reader cũ được xóa để không trình bày snapshot cũ như kết quả mới. Không có watcher,
  polling tự động hoặc ghi ngược từ UI vào Markdown.
- Có thể kéo nền, zoom, kéo node, **Vừa khung**, **Sắp lại** layout hoặc **Đặt lại**
  lựa chọn/tìm kiếm/filter. Các thao tác này không sửa file nguồn.

Graph gồm các file `.md` hợp lệ trong `raw/`, các bài trong `wiki/` và `wiki/index.md`.
Nó không nạp `wiki/log.md`, generated `Home.md`, `vault/`, inbox hoặc context riêng của
project. Review/verification records ở ngoài raw/wiki chỉ là đường dẫn metadata;
viewer không mở hoặc xác minh nội dung các file đó.

Starter hiện có **4 node, 9 cạnh**: một nguồn, hai bài và index. Portable vault có
**6 note, 14 cạnh** vì còn Home/log và quy tắc export riêng; hai số đếm không phải cùng
một dataset. Viewer đọc canonical trực tiếp, không cần refresh vault trước khi xem.
Workflow commit và staged hook vẫn yêu cầu refresh vault khi canonical thay đổi.

| Loại cạnh | Nguồn khai báo |
|---|---|
| `link` | Link Markdown inline giữa các note đủ điều kiện trong body. |
| `sources` | `metadata.sources`. |
| `claim` | Nguồn của một claim; giữ `claim_kind` và số record. |
| `contradiction` | Nguồn của một contradiction; giữ status và số record. |
| `supersedes`, `superseded_by` | Quan hệ thay thế do người biên soạn khai báo. |

Một cặp node có thể có nhiều cạnh với provenance khác nhau. Chúng là các khai báo cụ
thể, không phải quan hệ suy ra từ similarity hoặc bằng chứng rằng hai claim đúng.
Cạnh claim nét chấm biểu thị claim được gắn nhãn inference; quan hệ vẫn là khai báo
tường minh. Viewer giữ cả bài superseded/deprecated để đọc lịch sử, khác query CLI
chỉ trả các bài còn được sử dụng.
Link trong fenced/inline code không tạo cạnh. Reference-style links, wikilinks và
mọi biến thể CommonMark không nằm trong hợp đồng trích graph của MVP. Link ra ngoài
nhóm note được phép không khiến backend đọc thêm file hoặc truy cập mạng.

## Snapshot và tính mới

Mỗi `GET /api/graph` đọc lại canonical và tạo graph trong bộ nhớ. UI hiển thị revision
Git nếu đọc được trong root, thời gian sửa file index và thời gian load snapshot theo UTC. Revision là
**HEAD**, không chứng minh working tree sạch hoặc toàn bộ nội dung đã commit. Thời gian
index là mtime trên filesystem, không phải ngày kiểm chứng kiến thức. API còn có
`source_digest` để nhận diện byte của các input đã đọc.

Backend đọc hai lượt và từ chối khi phát hiện dữ liệu đổi giữa lúc load. Đây không
phải filesystem snapshot có khóa: hãy phối hợp với editor/writer và tải lại nếu
báo concurrent change. Viewer không thay thế `wiki.py lint --base ACCEPTED_SHA`,
review ngữ nghĩa hoặc kiểm tra staged trước commit. Nó không kiểm tra log/history,
quyền sử dụng thực tế hoặc tính đúng của claim.

## Demo nhiều topic

Tạo fixture riêng ở một destination mới, có parent tồn tại và không qua symlink:

```sh
python3 scripts/viewer_demo.py --output ../viewer-demo --topics 8
python3 scripts/viewer.py --root ../viewer-demo --check
python3 scripts/viewer.py --root ../viewer-demo --port 8766
```

`viewer_demo.py` nhận `--output NEW_DIRECTORY`, `--topics N` (mặc định 8; 1–200),
và `--date YYYY-MM-DD` tùy chọn để tái tạo byte với cùng ngày. Ngày phải hợp lệ và
không ở tương lai; mặc định là ngày UTC hiện tại. Không dùng lại destination đã có.
Ví dụ dùng `../viewer-demo` để tránh alias symlink `/tmp` trên macOS.

Mỗi topic có hai nguồn, ba concept và một lesson; thêm một index chung và log rỗng.
Với N topic, viewer có `6N + 1` node và `28N + min(3, N - 1)` cạnh có loại/provenance.
Mặc định 8 topic cho **49 node, 227 cạnh**; 200 topic cho 1.201 node, 5.603 cạnh.
Các số đếm mô tả fixture, không phải cam kết hiệu năng trình duyệt.

Tất cả đều gắn **SYNTHETIC DEMO**: nguồn và số liệu bịa để thử UI, có draft, bài bị
thay thế, inference và contradiction mở theo phiên bản. Không coi chúng là kiến thức
production. Generator không init/commit Git, gọi model, tải mạng hoặc nhập nội dung
vào wiki thật. Demo này khác `scripts/demo.py`, vốn kiểm tra workflow Git/submodule A/B.

## Biên an toàn và giới hạn

Server chỉ bind `127.0.0.1`, kiểm tra Host/Origin và ngữ cảnh request cùng origin.
Chỉ nhận GET/HEAD; không có API ghi, chọn đường dẫn file tùy ý hoặc thực thi lệnh từ
note. Các route static là allowlist cố định. Snapshot chỉ đọc file Markdown thường;
đường dẫn/symlink không hợp lệ và metadata project/private làm load thất bại.
Root cũng không được đi qua symlink. Đường dẫn `.git` không được phục vụ; backend chỉ
đọc `.git/HEAD` cùng loose/packed refs nằm trong root để lấy revision. Không chạy Git
subprocess, đọc config hoặc đi theo gitfile/worktree metadata ra ngoài root.

Giao diện dùng Markdown renderer và sanitizer local, không cho HTML trong note trở
thành mã thực thi. CSP hạn chế resource về cùng origin và chặn ảnh, font, object,
frame; không tự tải CDN, telemetry hoặc tài nguyên nhúng từ nguồn. Link HTTP(S) trong
body/origin chỉ mở tab ngoài khi người dùng bấm, với `noopener noreferrer` và không
gửi referrer; đây là điều hướng do người dùng chọn. Các ràng buộc này cần
được đánh giá bằng test riêng, không đồng nghĩa bảo đảm an toàn trước mọi nội dung.
Loopback không phải đăng nhập/phân quyền giữa các process local: người hoặc chương
trình có quyền trên máy có thể truy cập server khi nó đang chạy. Toàn bộ snapshot
note đủ điều kiện được gửi tới trình duyệt; metadata `approved` tự khai không phải
cơ chế ẩn secrets. Không dùng viewer như dịch vụ chia sẻ qua tunnel/proxy.

| Giới hạn backend hiện tại | Ngưỡng |
|---|---|
| Note trong một snapshot | 2.000, gồm index. |
| Cạnh tường minh trong một snapshot | 20.000. |
| Dung lượng mỗi note | 1 MiB. |
| Tổng byte note | 32 MiB. |
| Entry thư mục được duyệt | 8.000. |
| Độ sâu dưới raw/wiki | Tối đa 24 bước thư mục. |
| Load graph đồng thời | Một; request khác nhận HTTP 503 và cần thử lại. |

Các ngưỡng trên là guard khi đọc, chưa phải benchmark hoặc SLA. Nền tảng phải có
`O_NOFOLLOW`, `O_DIRECTORY` và hỗ trợ đọc bằng directory file descriptor; môi trường
không hỗ trợ bị từ chối. Không hứa tương thích Windows. Lỗi HTTP trả thông báo tổng
quát, không trả nội dung nguồn, đường dẫn tuyệt đối hoặc lỗi hệ điều hành.

Nếu port bận, chọn `--port 8766` hoặc `--port 0`. Nếu HTTP 403, dùng URL chính xác
được in ra, không qua proxy/iframe. HTTP 409 yêu cầu load lại sau khi editor ổn định;
HTTP 422 báo snapshot không hợp lệ hoặc vượt giới hạn. Dùng `wiki.py lint` tại root
đó để điều tra canonical, sửa qua workflow đóng góp rồi tải lại. Viewer không tự
sửa index, raw hoặc log để vượt qua lỗi.

## Thư viện và phạm vi tiếp theo

| Thư viện đã vendored | Phiên bản | License |
|---|---|---|
| Cytoscape.js | 3.34.4 | MIT. |
| markdown-it | 15.0.3 | MIT. |
| DOMPurify | 3.4.17 | MPL-2.0 hoặc Apache-2.0. |

Các distribution lấy từ official npm registry, giữ nguyên file phân phối và license;
[manifest](../viewer/vendor/manifest.json) ghi URL gốc, integrity và SHA-256.
Không cần cài npm hoặc chạy build khi dùng viewer. Giao diện và code tích hợp được
viết cho repo này; không sao chép code, asset hoặc branding của Graphify.

P0 tập trung graph, tìm title/ID, filter, reader, provenance và Refresh thủ công.
Chưa có full-text search, mở rộng nhiều hop, tìm đường đi, copy context hoặc bảng
diagnostics (P1); clustering, Git diff, auto-refresh và export của viewer (P2) cũng
chưa triển khai. Portable export hiện có vẫn dùng `scripts/export_vault.py`.

Xem [báo cáo validation, ảnh browser và benchmark](VIEWER-VALIDATION-20261018.md):
197 tests Python và 10 nhóm browser tests đã pass trên môi trường được ghi rõ trong báo cáo.
Có tính năng hoặc chạy `--check` không tự chứng minh mọi nền tảng/nội dung đều được kiểm chứng.
Xem thêm [ADR 003](ADR-003.md), [CLI](CLI.md) và [policy](POLICY.md).
