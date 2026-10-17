# Kiểm tra hướng dẫn README — 2026-10-17 UTC

Đợt này chỉ sửa README/docs để mô tả đúng implementation tại public baseline
`67e8bfb22a3281092c0e4bded0a3b702b279b486`. Không đổi code, raw/wiki/vault, config,
auth hoặc cài thêm tích hợp. Nhánh tài liệu: `contrib/readme-guide`; dừng trước push.

## Thay đổi

README tiếng Việt bổ sung overview, kiến trúc, prerequisites, quy trình biên soạn/review,
CLI thực có, demo, submodule/worktree/pin/rollback, hooks, Obsidian, troubleshooting và bảo mật.
Các docs liên quan sửa publication record đã lỗi thời, thứ tự stage conflict trước khi index,
khôi phục vault generated khi merge, giữ đủ event log và chọn đúng cwd project khi commit pin.

Phân biệt rõ: `record ingest/review` chỉ ghi log; tổng hợp và review vẫn do người/agent thực hiện.
Hooks có điều kiện cài/trust; chưa chứng minh native agent activation. Vault là bản đọc sinh ra,
không có đồng bộ hai chiều; chưa chạy GUI Obsidian/Logseq. Không có workflow CI được cài.

## Đã chạy trong đợt tài liệu

[Smoke evidence](evidence/readme-smoke-20261017.json): **11 kịch bản pass, 113 subprocess calls**.
Đây là smoke test với fixture tổng hợp và Git thật, không phải 113 unit tests hoặc test LLM.

- Quickstart: lint có baseline, query v1 đúng nguồn, v2 rỗng ở starter, vault check.
- Help của các entrypoint/subcommand khớp cú pháp được viết.
- Install/status/check/uninstall Git hooks trong clone tạm; commit thực chạy hook.
- Ingest fixture v2: nguồn mới, sửa concept/index/log, báo mâu thuẫn, raw v1 không đổi.
- `record` và `--record`: ghi log, refresh/stage vault rồi commit thành công.
- Hai nhánh conflict log/vault: giữ event hai bên, stage canonical, restore riêng generated
  vault, tái tạo, lint hai parent, commit merge trên contrib rồi fast-forward main.
- Bootstrap consumer, fetch local, nâng pin và rollback bằng CLI.
- Clone consumer với `--recurse-submodules` và `update --init --recursive`.
- Export vault riêng, check và refresh.
- Demo đầy đủ và các query sau demo: A/B khác pin, đúng nguồn/version, raw giữ nguyên,
  dữ liệu project ở local, rollback và snapshot vault đúng.

Toàn bộ thao tác ghi/test trên repo tạm. Git remote trong smoke là đường dẫn local thay cho URL
GitHub; `protocol.file.allow=always` chỉ áp dụng từng lệnh sandbox. Không gọi mạng remote,
đổi config repo làm việc, gửi dữ liệu nguồn hoặc push. Harness tạm không trở thành test mới của sản phẩm.

Review độc lập đối chiếu docs với code và phát hiện hai lỗi hướng dẫn: cwd sau pin và diễn đạt
lọc event log trùng. Cả hai đã được sửa. Link/anchor nội bộ và shell fences được kiểm tra lại
sau chỉnh sửa; số lượng cuối cùng ghi trong [evidence](evidence/readme-smoke-20261017.json).
Lệnh Git hook kiểm tra staged snapshot và `git diff --check` được chạy trước commit tài liệu.

## Giới hạn bằng chứng

Mốc **154 unit/integration tests pass** thuộc đợt triển khai trước, xem
[báo cáo vault](VIEWING-VALIDATION-20261017.md). Không chạy lại toàn bộ suite trong đợt docs này
vì implementation không đổi; smoke tập trung vào các hướng dẫn mới/sửa.

Không test GUI Obsidian, native Codex/Claude activation, LLM ingest/review thực hoặc CI. Không
kiểm tra lại trạng thái GitHub/auth/publication trong đợt này. Chỉ đối chiếu hướng dẫn trust hooks
với [OpenAI Docs](https://learn.chatgpt.com/docs/hooks); không kiểm tra toàn bộ URL bên ngoài.
Mermaid được viết ở dạng Markdown; không có kiểm tra render bằng trình duyệt trong đợt này.
