# Viewer graph local

Viewer mở graph và nội dung canonical ngay trong trình duyệt, chỉ đọc qua HTTP tại
`127.0.0.1`. Không cần Obsidian, Node.js, npm, API key hoặc dịch vụ LLM để chạy.
Python dùng thư viện chuẩn; các thư viện giao diện đã có sẵn trong `viewer/vendor/`.
Viewer chỉ chạy khi bạn chủ động mở server; không tự publish hoặc bật server nền.

## Chạy và dừng

Từ root clone có mã viewer:

```sh
python3 scripts/viewer.py --check
python3 scripts/viewer.py
```

`--check` đọc và kiểm tra snapshot, in JSON gồm số node/cạnh, fingerprint, revision,
cảnh báo và số chẩn đoán; không mở HTTP hoặc tạo file export. Lệnh thứ hai in URL
`http://127.0.0.1:8765/`. Mở đúng URL đó; dùng **Ctrl+C** trong terminal để dừng server.
Không dùng `localhost`: kiểm tra Host của server yêu cầu đúng `127.0.0.1:PORT`.

Cú pháp đầy đủ:

```text
python3 scripts/viewer.py [--root ROOT] [--port PORT] [--check]
```

Root mặc định là repo chứa `scripts/viewer.py`, không phải cwd của shell. `--port` mặc
định 8765, nhận 0–65535; 0 yêu cầu hệ điều hành chọn cổng trống, xem URL thực tế in ra.
Không có option đổi host hoặc `--export`. Mã thoát là 0 khi check không có error diagnostic
hoặc dừng bằng Ctrl+C; 1 khi check có error diagnostic như nguồn khai báo bị thiếu;
2 khi sai tham số, snapshot bị từ chối hoàn toàn hoặc không mở được server.

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

- Tìm toàn văn trong title, ID/đường dẫn, summary, body và claim, không phân biệt hoa
  thường/dấu tiếng Việt. Kết quả ghi trường khớp và đoạn trích; đây là tìm chuỗi,
  không phải tìm kiếm ngữ nghĩa. Dùng ↑/↓ và Enter để chọn, Escape để xóa tìm kiếm.
- Lọc theo loại node và topic/tag: node phải khớp một loại đã chọn và ít nhất một tag
  đã chọn. Nhóm **Không có tag** dành cho note không gắn tag. Filter quan hệ chỉ ẩn
  cạnh, không tự ẩn node. Số cạnh/node ở header là đang hiện/tổng; số cạnh/tag trong
  checkbox đếm toàn snapshot. Filter chỉ điều khiển hiển thị, không phân quyền dữ liệu.
- Lọc trạng thái để xem các note đang dùng hoặc đã superseded/deprecated. **Đang dùng**
  chỉ loại các trạng thái đã thay thế; không có nghĩa nội dung đã được kiểm chứng.
  Nguồn cũ không tự bị ẩn vì có phiên bản mới: viewer không suy ra nguồn nào là đúng nhất.
- Chọn node để đọc nội dung, metadata, các cạnh đi ra và backlink. Nhãn fixture,
  status, phiên bản và evidence/inference/unknown vẫn phải được đọc cùng claim.
- Chọn cạnh để xem loại quan hệ và nơi khai báo, ví dụ `metadata.sources` hoặc
  `metadata.claims[0].sources`. Cạnh từ link Markdown có provenance `body`, chưa có
  số dòng hoặc vị trí heading chính xác.
- Tab **Liên kết** liệt kê cạnh đi ra/backlink của toàn snapshot, kể cả cạnh bị ẩn
  bởi filter. Chọn tham chiếu để chuyển sang note hoặc xem chi tiết cạnh.
- Dùng **Tải lại dữ liệu** sau khi sửa canonical để nạp snapshot mới. Nếu load thất
  bại, graph/reader cũ được xóa để không trình bày snapshot cũ như kết quả mới. Mặc định
  không tự polling; có thể bật **Tự tải lại** theo hướng dẫn bên dưới. Không ghi ngược vào Markdown.
- Có thể kéo nền, zoom, kéo node, **Vừa khung**, **Sắp lại** layout hoặc **Đặt lại**
  lựa chọn/tìm kiếm/filter. Các thao tác này không sửa file nguồn.

### Khám phá, citation và lịch sử

Nhóm **Khám phá liên kết** cho phép xem lân cận 1–2 hop, tìm đường giữa hai note và
lần theo nguồn. Kết quả dùng các cạnh thực đang đủ điều kiện qua filter, ghi rõ chiều
duyệt, loại quan hệ và provenance. Đường đi là cách điều hướng, không phải giải thích
nhân quả hay chứng nhận claim. Không có đường phù hợp thì báo không tìm thấy; viewer
không bổ sung quan hệ để nối hai note. Giữ index trong filter có thể nối nhiều topic
qua trang điều hướng; hãy bỏ loại điều hướng nếu muốn tập trung vào nội dung.

**Sao chép context có nguồn** tạo văn bản có đường dẫn canonical, nhãn claim, phiên
bản, snapshot và citation. Kiểm tra bản xem trước và cảnh báo thiếu bằng chứng/cắt
ngắn trước khi dán. Chỉ thao tác sao chép mới yêu cầu ghi clipboard; viewer không gửi
nội dung tới LLM hay dịch vụ khác, không lưu câu trả lời trở lại wiki.

Chọn note/cạnh và tab reader cập nhật fragment URL; có thể dùng Back/Forward hoặc
mở deep link trên cùng wiki. ID không còn trong snapshot được xử lý như lựa chọn
không tồn tại, không dùng URL làm đường dẫn để đọc thêm file. URL không chứa body.
Đổi root hoặc commit có thể làm liên kết cũ không còn phù hợp.

### Chẩn đoán cấu trúc

Bảng chẩn đoán báo link nội bộ đủ phạm vi nhưng thiếu đích, nguồn được khai báo nhưng
không có, bài thiếu liên kết đi vào và index lệch. Không tạo node/cạnh giả cho các đích
thiếu. Tham chiếu ngoài raw/wiki, log và file riêng của project không được mở để kiểm tra.
Orphan ở đây xét liên kết từ bài khác, bỏ qua index và self-link; chỉ là tín hiệu bảo trì.
Khi index lệch, viewer giữ chẩn đoán nhưng không trả body hoặc tạo cạnh từ body index
đó. Index có frontmatter/private metadata không đúng quy ước là lỗi dừng; các bài
đủ điều kiện còn lại không được dùng để hợp thức hóa nội dung index chưa kiểm tra.

Snapshot có chẩn đoán thiếu nguồn được ghi rõ **thiếu bằng chứng**, không trở thành
snapshot đã được xác minh chỉ vì còn render được. Private scope, đường dẫn không an
toàn, symlink, cấu trúc metadata/claim không hợp lệ và sai version của nguồn hiện có
vẫn là lỗi dừng toàn bộ. Sửa canonical bằng workflow đóng góp; viewer không sửa tự động.

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
Git nếu đọc được trong root, thời gian sửa file index và thời gian load snapshot. API
ghi timestamp ISO theo UTC; giao diện định dạng theo múi giờ của trình duyệt. Revision là
**HEAD**, không chứng minh working tree sạch hoặc toàn bộ nội dung đã commit. Thời gian
index là mtime trên filesystem, không phải ngày kiểm chứng kiến thức. API còn có
`source_digest` để nhận diện byte của các input đã đọc.

Backend đọc hai lượt và từ chối khi phát hiện dữ liệu đổi giữa lúc load. Đây không
phải filesystem snapshot có khóa: hãy phối hợp với editor/writer và tải lại nếu
báo concurrent change. Viewer không thay thế `wiki.py lint --base ACCEPTED_SHA`,
review ngữ nghĩa hoặc kiểm tra staged trước commit. Nó không kiểm tra log/history,
quyền sử dụng thực tế hoặc tính đúng của claim.

## Nhóm, bố cục và tự tải lại

**Nhóm & bố cục** có hai cách gom nhóm: theo loại nội dung hoặc theo tag ít phổ biến
nhất trong tập note qua filter; tag bằng nhau chọn theo thứ tự ký tự. Đây là phép nhóm
xác định từ metadata, không phải kết quả LLM hoặc phát hiện cộng đồng ngữ nghĩa. Node
nhóm và cạnh gộp được đánh dấu dẫn xuất. Mở nhóm để xem note/cạnh gốc và provenance;
chọn một note qua tìm kiếm hoặc tham chiếu sẽ mở nhóm chứa note đó.

Thu gọn không phải filter riêng tư. Số note/cạnh canonical vẫn tách khỏi số đối tượng
nhóm vẽ trên canvas. Khi hơn 500 node đang được bố trí, viewer dùng lưới xác định để
tránh force layout đồng bộ chậm; vị trí và khoảng cách không diễn tả mức liên quan.
Graph nhỏ dùng bố cục lực. **Sắp lại** tôn trọng cùng giới hạn.

**Lưu bố cục & bộ lọc** lưu ID, tọa độ, zoom/pan và tùy chọn trong localStorage của
origin hiện tại, tối đa 1 MiB. Dữ liệu lưu được kiểm tra khi đọc; không lưu body note,
raw hay toàn bộ snapshot. Khóa riêng dùng định danh corpus mờ từ identity filesystem,
không trả đường dẫn root. Đổi máy/clone/root hoặc cổng có thể không thấy bản lưu cũ.
**Khôi phục** chỉ áp dụng ID còn hợp lệ; **Xóa bản lưu** chỉ xóa bản của corpus này.

**Tự tải lại** mặc định tắt; chọn 15, 30 hoặc 60 giây. Tab ẩn tạm dừng; request đang
chạy không bị một lượt polling khác chồng lên. Dữ liệu không đổi không chạy lại layout.
Khi dữ liệu đổi, giữ selection/filter/vị trí còn hợp lệ và bố trí note mới. Snapshot lỗi
xóa graph/reader, comparison và ý định export cũ, đồng thời tắt tự tải lại. Lựa chọn bật
tự tải lại không được lưu qua lần mở trang mới. Không có daemon sau khi đóng viewer.

## So sánh revision Git

Trong phần công cụ dữ liệu, nhập **hai SHA commit đầy đủ** thuộc lịch sử HEAD local
rồi chọn **So sánh**. Không dùng tên nhánh, `HEAD~1`, đường dẫn, tag hoặc SHA rút gọn.
Đây là diff của graph tri thức, không phải diff code của cả repo: commit chỉ sửa viewer
có thể cho kết quả 0 thay đổi kiến thức. UI không checkout, merge hoặc cập nhật pin.

Kết quả gồm note/cạnh thêm, bỏ, thay đổi; các trường đổi được nêu tên. Node lịch sử chỉ
trả summary metadata đủ điều kiện, không trả body/metadata object nguyên bản. Cạnh giữ
loại, chiều và provenance. Version/claim khác nhau không được diễn giải thành nguồn mới
đúng hơn. Hai snapshot đều phải qua kiểm tra; một nguồn private trong revision cũ cũng
làm toàn bộ compare bị từ chối. Index bị giữ lại có chẩn đoán như graph thông thường.

Compare chỉ hỗ trợ `.git/` thật bên trong root. Submodule/worktree dùng gitfile, history
thiếu object hoặc vượt giới hạn không được mở rộng sang thư mục khác/fetch mạng. Backend
sao chép object regular được cho phép vào thư mục tạm private có giới hạn, dùng Git để
đọc object tại đó rồi dọn. Không đọc config/hook/alternate/replacement refs của repo gốc.
Không gửi nội dung ra ngoài máy hoặc sửa Git state gốc.

| Giới hạn compare | Ngưỡng |
|---|---|
| Byte object store được copy | 256 MiB; mỗi file tối đa 128 MiB. |
| Git objects / commits trong ancestry | 10.000 / 2.000. |
| Commit giải nén | 1 MiB mỗi commit; tổng 16 MiB. |
| Tree metadata giải nén | 2 MiB mỗi snapshot. |
| Thời gian một compare | 20 giây, kiểm tra trong quá trình đọc/chạy subprocess. |
| JSON response compare | 10 MiB. |

Giới hạn note/cạnh/diagnostic của graph vẫn áp dụng cho từng revision. Repo lớn hơn
có thể bị từ chối dù corpus hiện tại nhỏ. Đây là hỗ trợ Git local có giới hạn, không
phải dịch vụ duyệt mọi history/remote hoặc cam kết xử lý mọi object store hỏng.
Kiểm tra kích thước trước khi đọc giới hạn object được yêu cầu và response, không
đặt trần RSS cho Git: một packed delta nhỏ có thể cần giải nén base lớn bên trong.
Giới hạn 20 giây được kiểm tra khi đọc/chạy subprocess, không phải watchdog riêng
cho mọi thao tác của hệ điều hành hoặc bộ cấp phát bộ nhớ.

## Xuất JSON và ảnh

**Xuất JSON** hoặc **Xuất PNG** mở hộp xác nhận với phạm vi cụ thể. File có thể chứa tên
tài liệu, nguồn hoặc nội dung cần kiểm soát: kiểm tra trước khi chia sẻ. Không có upload
tự động. Hủy không tạo file tải xuống; snapshot/filter đổi thì cần xác nhận lại.

- JSON chứa các note/cạnh canonical qua filter và vùng khám phá hiện tại, **kể cả thành
  viên nhóm thu gọn**. Nhóm UI nằm riêng và được đánh dấu dẫn xuất. Không chứa comparison,
  snapshot cũ hoặc note ngoài phạm vi. Giới hạn file 64 MiB.
- PNG chụp graph đang hiển thị, không chụp reader hay toàn màn hình; tối đa 2048×2048 pixel
  và 20 MiB. Nhãn nhóm vẫn thể hiện đây là cách trình bày dẫn xuất.

Export browser khác `scripts/export_vault.py`: không tạo một nguồn wiki mới, không cập
nhật vault, Git hoặc log và không được dùng bản xuất làm bằng chứng độc lập khi ingest.

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
đọc `.git/HEAD` cùng loose/packed refs nằm trong root để lấy revision của graph. Chỉ
compare chủ động mới dùng Git subprocess trên bản object tạm cô lập; không đọc config
gốc hoặc đi theo gitfile/worktree metadata ra ngoài root.

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
| Chẩn đoán cấu trúc trong một snapshot | 10.000; UI hiển thị tối đa 100. |
| Dung lượng mỗi note | 1 MiB. |
| Tổng byte note | 32 MiB. |
| Entry thư mục được duyệt | 8.000. |
| Độ sâu dưới raw/wiki | Tối đa 24 bước thư mục. |
| Load graph/compare đồng thời | Một; request khác nhận HTTP 503 và cần thử lại. |

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

P0 cung cấp graph, filter, reader, provenance và Refresh thủ công. P1 bổ sung tìm toàn
văn, khám phá hop/đường đi/nguồn, lọc trạng thái, copy context, diagnostics và lịch sử
điều hướng. P2 bổ sung nhóm xác định, layout lưu tại browser, Git diff có giới hạn,
auto-refresh chủ động và export JSON/PNG có xác nhận.
Portable export hiện có vẫn dùng `scripts/export_vault.py`.

Các báo cáo [MVP](VIEWER-VALIDATION-20261018.md), [P1](VIEWER-P1-VALIDATION-20261018.md)
và [P2](VIEWER-P2-VALIDATION-20261018.md) ghi kết quả test, ảnh browser và benchmark
của từng giai đoạn, với môi trường và giới hạn cụ thể.
Xem [checklist phát hành](VIEWER-RELEASE-20261018.md) để biết kiểm thử hồi quy cuối,
clipboard/tab ẩn và phạm vi publication đã được phê duyệt.
Có tính năng hoặc chạy `--check` không tự chứng minh mọi nền tảng/nội dung đều được kiểm chứng.
Xem thêm [ADR 003](ADR-003.md), [ADR 004](ADR-004.md), [ADR 005](ADR-005.md), [CLI](CLI.md) và [policy](POLICY.md).
