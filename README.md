# CapCut Harness

**Một plugin cho Codex local: thêm cinematic card, cân thoại từng nguồn và gửi yêu cầu tự nhiên về chính chat đang mở.**

[English](README.en.md) · [v0.3.0](https://github.com/Ductoii/capcut-cinematic-cards/releases/tag/v0.3.0) · [MIT](LICENSE)

## Cài một dòng

Máy có Codex desktop, Python 3.10–3.13 và FFmpeg/ffprobe:

```bash
curl -fsSL https://raw.githubusercontent.com/Ductoii/capcut-cinematic-cards/v0.3.0/install-harness.py | python3
```

Không rành Terminal? Gửi link repo cho Codex **trên máy có project**, nói: “Cài CapCut Harness v0.3.0, chuẩn bị dependency và mở workspace. Không computer use.” Codex thực hiện phần cài đặt; không cần sửa JSON.

Bộ cài tạo runtime riêng, đăng ký plugin/MCP bằng CLI của Codex và gộp card + audio vào skill `capcut-harness`. Bản cũ do bộ cài quản lý được sao lưu. Service cũ chỉ dừng khi không có job đang chạy và xác định đúng tiến trình thuộc bộ cài. Không tắt CapCut.

## Dùng trong Codex

Sau khi cài, mở **chat Codex local mới** và gửi:

```text
$capcut-harness
Mở workspace cho project 1027.
```

Plugin cần host hỗ trợ MCP Apps và `ui/message`. Panel có chọn project, card, cân thoại, nghe A/B, Apply/Undo và ô gửi yêu cầu. Ô này gửi lời nhắn vào **chính chat chứa panel**; Codex dùng công cụ như khi bạn nhắn trực tiếp. Nó không gọi một model thứ hai. Host có thể yêu cầu xác nhận gửi; quyết định đó thuộc Codex.

Ví dụ:

- “Chỉ thêm time/location card thật sự cần ở các đoạn chuyển mờ đen, tránh thoại và cảnh quan trọng.”
- “Giới thiệu nhân vật chính ở lần xuất hiện đầu, có tên và vai trò, chữ hợp phim này.”
- “Cân thoại giữa các clip cho đều và rõ; giữ sắc thái diễn xuất, hình và clip ghép.”

Yêu cầu có trạng thái đã lưu, đã gửi, đã nhận, đang làm và kết quả. Khi host chưa xác nhận gửi, panel báo chưa rõ trạng thái và không tự gửi lại. Các yêu cầu khác vẫn do Codex hiểu theo khả năng công cụ hiện có; không còn giới hạn ở vài mẫu câu.

**UI trình duyệt độc lập** (`~/.local/bin/capcut-harness`) vẫn dành cho công việc local và nghe audio, nhưng không có cầu nối chat. Dùng panel từ skill cho ô yêu cầu tự nhiên. Nếu tool chưa xuất hiện sau cài, nhờ Codex sửa đăng ký bằng `install-harness.py --register-only`; không sửa cấu hình tay. Hỗ trợ panel và cầu nối tùy phiên bản host; cài thành công không đồng nghĩa đã chứng minh host hiển thị/gửi tin thành công.

## Cân thoại cho phim online

Preset mặc định dùng **−16 LUFS làm mốc thoại, trần −1,5 dBTP**, stereo 48 kHz PCM24. Đây là lựa chọn khởi đầu cho phim online, không phải chứng nhận hay một chuẩn bắt buộc chung cho mọi phim/MV YouTube. Vạch vàng chỉ cho biết peak tức thời, không đủ so độ to cảm nhận giữa các nguồn.

Harness xử lý:

1. Tách theo từng nguồn đang nghe được trên timeline; giữ trim, tốc độ đều, volume và fade được hỗ trợ.
2. Nhận diện thoại trên từng nguồn, tăng mức riêng cho đầu vào detector khi cần; mức tăng này không tự đi vào audio đầu ra.
3. Cân mỗi take theo trung vị LUFS có trọng số thời lượng; tinh chỉnh câu trong biên độ nhỏ để giữ diễn xuất.
4. Nén RMS nhẹ 2:1, attack 15 ms/release 180 ms để thu các âm tiết vọt lên; bù mức có giới hạn.
5. Bảo vệ peak từng nguồn, trộn lại rồi giới hạn peak master. Nguồn không nhận diện thoại được giữ mức và báo riêng.

Mức bù tối đa mặc định 48 dB giúp các file rất nhỏ vẫn có thể được cân; đồng thời có thể kéo cả noise lên. Nhạc/SFX nằm ở track riêng không bị kéo theo gain của thoại. Nhạc, tiếng nền hay giọng hát đã trộn vào cùng một file vẫn đi theo file đó; không có tách stem hoặc nhận dạng nhân vật từ giọng.

Bấm **Cân âm thoại** để chuẩn bị bản nghe; project chưa thay đổi. Có thể nghe A/B, đổi mục tiêu, bỏ chọn khoảng nhận nhầm rồi cập nhật. Khoảng bỏ chọn lấy lại audio nguồn trước khi trộn; limiter master vẫn áp dụng toàn bản. Báo cáo hiển thị độ phủ nguồn, khoảng còn lệch và các trường hợp cần chú ý. Không tự chạy thêm một vòng kiểm tra/nghe cả phim ngoài công việc được yêu cầu.

Khi áp dụng, **lưu và đóng CapCut**. Harness thêm một master audio ngoài clip ghép, tắt âm các đoạn gốc tham gia mix để tránh phát đôi, giữ hình, cấu trúc compound và card. Undo dùng backup chính xác và từ chối ghi đè nếu có chỉnh sửa mới. Không xóa `~/.local/share/capcut-harness`: đây là nơi lưu job, bản nghe và backup; phim dài có thể tốn nhiều GB.

## Cinematic card

- Time/location chỉ khi cần định hướng; ưu tiên fade đen có sẵn đủ thời gian đọc, không kéo dài fade để nhét chữ.
- Giới thiệu nhân vật tại lần xuất hiện đã xác nhận, gồm tên + vai trò ngắn đã có bằng chứng; không đoán tên, bịa nghề hoặc tiết lộ twist.
- Chọn font cài sẵn, màu, cỡ, spacing, vị trí và opacity fade hợp thể loại; mỗi phim có thể khác nhau.
- Thêm text native ở root track riêng; không sửa clip ghép, cảnh, thoại hoặc transition gốc. Helper hỗ trợ dựng plan/stage/backup/restore; không có gói hiệu ứng glitch hay chữ chuyển động phức tạp.

Codex đọc kịch bản/phụ đề và frame để quyết định vị trí. Không phải công cụ nhận mặt bảo đảm đúng mọi nhân vật. [Hướng dẫn card](skills/capcut-harness/references/cards.md) · [Lệnh/plan](skills/capcut-harness/references/tool.md).

## Phạm vi và tình trạng

Project JSON local đọc được, schema `360000`; không hỗ trợ draft mã hóa hoặc audio routing/effect/tốc độ biến thiên chưa hiểu rõ. Chạy bằng file và công cụ local; không Computer Use, không API key âm thanh. Audio không được upload bởi harness; lời nhắn và kết quả tool vẫn đi qua chat Codex như bình thường.

v0.3.0 có kiểm tra cú pháp/đóng gói và cài plugin local; không thực hiện vòng 300 nguồn hoặc nghe/kiểm tra lại phim thật theo yêu cầu chủ dự án. Các kết quả kiểm thử v0.2.0 trong [lịch sử](docs/verification.md) không phải bằng chứng cho engine mới. Audio dựng từ nguồn không chứng minh playback/export native CapCut; báo cáo giữ `editor_render_verified: false`. Không khôi phục được tiếng đã méo trong file gốc. macOS là môi trường phát triển; các hệ điều hành khác chưa được xác minh.

[Kiến trúc phát triển](docs/harness-development.md) · [Quyết định](docs/review-and-decisions.md) · [Bản card độc lập cũ v0.1.1](https://github.com/Ductoii/capcut-cinematic-cards/tree/v0.1.1)
