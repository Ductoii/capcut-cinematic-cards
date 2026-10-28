# CapCut Cinematic Cards

**Cân âm thanh dùng tool riêng:** [CapCut Audio](https://github.com/Ductoii/capcut-audio), chạy local bằng thuật toán, không cần Codex. Repo này chỉ giữ skill card độc lập.


**Bảo Codex thêm time card, location card và giới thiệu nhân vật cho phim CapCut — giữ nguyên clip ghép.**

[English](README.en.md) · [Hướng dẫn dành cho Codex](skills/capcut-cinematic-cards/SKILL.md) · [MIT](LICENSE)

Đây là **skill + công cụ Python chạy local**. Codex đọc phim/kịch bản, chọn chỗ cần chữ và cách trình bày; công cụ tạo text có thể sửa trong CapCut, sao lưu và kiểm tra dữ liệu. Không cần Computer Use, MCP hay API key riêng. Dùng model của phiên Codex hiện tại.

## Cài một dòng

**Mac/Linux**, có Python 3.10 trở lên:

```bash
curl -fsSL https://raw.githubusercontent.com/Ductoii/capcut-cinematic-cards/v0.1.1/install.py | python3
```

**Windows PowerShell**, có Python 3.10 trở lên:

```powershell
(Invoke-WebRequest -UseBasicParsing https://raw.githubusercontent.com/Ductoii/capcut-cinematic-cards/v0.1.1/install.py).Content | py -3 -
```

Không biết mở Terminal? Dán link repo này vào **Codex local trên máy có project**, nói: **“Cài skill này cho tôi và chuẩn bị dependency để dùng với CapCut.”** Codex có thể thực hiện lệnh cài giúp bạn. Lệnh tải và chạy mã nguồn công khai trong repo; có thể đọc [installer](install.py) trước khi chạy.

Skill được cài vào `~/.agents/skills/capcut-cinematic-cards` theo [quy ước skill của Codex](https://learn.chatgpt.com/docs/build-skills). Nếu chưa xuất hiện, khởi động lại Codex. Không cần clone repo hoặc sửa JSON. Chạy lại lệnh để cài lại bản 0.1.1; bản cũ được sao lưu. Lệnh được ghim phiên bản, không tự cập nhật sang bản mới.

## Dùng ngay

Mở chat Codex trên máy có CapCut/project rồi gửi:

```text
$capcut-cinematic-cards
Thêm time card và location card thực sự cần thiết cho project “Tên project”.
Thêm tên và vai trò ngắn cho nhân vật chính ở lần xuất hiện đầu tiên có thể xác nhận.
Chọn kiểu chữ cinematic phù hợp với chất phim, ưu tiên các đoạn chuyển mờ đen.
Không che cảnh quan trọng, mặt, phản ứng hay thoại; không động vào clip ghép của tôi.
Không computer use. Kịch bản và reference nhân vật ở: [đường dẫn hoặc file tôi gửi].
```

Thay tên project/nguồn bằng thông tin của bạn trong **tin nhắn**, hoặc gửi thẳng đường dẫn project. Bạn không phải tạo plan, chọn timestamp, sửa file draft hay viết code; Codex làm các bước đó. Nếu bạn không cần giới thiệu nhân vật, bỏ câu đó khỏi yêu cầu.

Nếu đã biết hướng mỹ thuật, nói thêm, ví dụ:

- “Drama gia đình cổ điển: serif màu ngà, chữ kín đáo, fade chậm.”
- “Thriller hiện đại: sans gọn, trắng lạnh, nhịp hiện dứt khoát.”
- “Phim tài liệu: chữ trung tính, ưu tiên đọc rõ và thông tin.”
- “Tình cảm: serif mềm, màu ấm, hiệu ứng nhẹ.”

Bản **0.1.1** bổ sung mặc định tên + vai trò, cỡ chữ 6.2/3.8 trong đơn vị CapCut và vị trí hai dòng -0.64/-0.77 cho card nhân vật; có thể tùy biến theo phim. Các card thời gian/địa điểm giữ mặc định riêng.

Codex lựa font có sẵn trên máy, màu, cỡ, khoảng cách, vị trí và thời gian fade theo phim. Có 5 điểm xuất phát: drama, thriller, tài liệu, tình cảm, noir; có thể tùy chỉnh từng card trong cùng hệ thống. Bản này tạo typography, bóng nhẹ và opacity fade; chưa có glitch, tracking động, freeze frame hay effect pack.

## Giới thiệu nhân vật có khả thi không?

**Có**, khi xác nhận được nhân vật và lần xuất hiện đầu. Codex đối chiếu kịch bản/reference, rà các cảnh trước đó rồi đặt tên ở khoảnh khắc yên sau khi người xem nhận ra nhân vật. Mặc định có **tên + vai trò ngắn** (nghề nghiệp hoặc quan hệ đã được xác lập), chữ vai trò nhỏ hơn tên nhưng vẫn đọc rõ. Không gắn nhãn phản diện hay tiết lộ tương lai của nhân vật. Nếu bạn chỉ muốn tên, vai trò chưa rõ hoặc có nguy cơ spoil, Codex ghi lý do và bỏ riêng dòng vai trò.

Không đoán tên từ khuôn mặt, không spoil người đang được giấu danh tính, không giới thiệu mọi nhân vật phụ. Nếu đoạn ra mắt có thoại hoặc phản ứng quan trọng, dời trong cùng cảnh hoặc bỏ card. Đây là lựa chọn biên tập của Codex dựa trên bằng chứng, không phải công cụ tự nhận diện khuôn mặt chính xác tuyệt đối.

## Chuẩn bị trên máy khác

| Cần có | Để làm gì |
|---|---|
| Codex local có quyền đọc file và chạy terminal | Phân tích, chọn card và gọi công cụ |
| Python 3.10+ | Cài và chỉnh dữ liệu project, chỉ dùng thư viện chuẩn |
| FFmpeg + ffprobe trên PATH | Trích khung hình/âm thanh quanh vị trí dự kiến |
| Project CapCut local và media gốc còn truy cập được | Đọc timeline, xem cảnh, nghe thoại |
| Kịch bản/caption/reference có thể xác minh | Xác định thời gian, địa điểm và nhân vật |
| Font local hỗ trợ ngôn ngữ của phim | Hiển thị chữ đúng; repo không kèm font |

Nhờ Codex kiểm tra/chuẩn bị phần thiếu qua terminal. Không cần tài khoản dịch vụ nhận diện hay key trả phí khác. Một phiên chat cloud không truy cập được file trên máy sẽ không thể xử lý project local.

**Lưu và đóng CapCut trước khi áp dụng.** Codex có thể phân tích và tạo bản chờ trước; công cụ sẽ từ chối ghi nếu editor đang chạy, không tự kill app. Nếu có thay đổi chưa lưu, phải lưu an toàn trước khi tiếp tục.

## Bảo vệ phim đang dựng

- Chỉ thêm các track text riêng bên ngoài compound clip; giữ nguyên clip ghép, âm thanh, thời lượng và chuyển cảnh gốc.
- Chọn card cần thiết. Mặc định khoảng 3.2–3.6 giây, không ép chữ vào fade 1.5 giây bằng cách kéo màn đen che cảnh.
- Xem vùng trước/sau và toàn thời gian chữ hiện; tránh mặt, bàn tay, đồ vật, phụ đề, thoại và các phản ứng quan trọng.
- Sao lưu bên ngoài project trước khi ghi. Kiểm tra hash, dữ liệu gốc và các mirror của timeline; chặn ghi đè khi project đã thay đổi.
- Chạy lại chỉ thay card do skill quản lý chính xác. Nếu bạn hoặc CapCut đã sửa/chuẩn hóa chúng, công cụ dừng để Codex đối chiếu, không ép ghi đè.
- Có khôi phục có kiểm tra. Bảo Codex: **“Khôi phục lần thêm card vừa rồi từ bản sao lưu, giữ các thay đổi tôi làm sau đó.”** Nếu xung đột, công cụ giữ thay đổi mới và báo rõ; không hứa rollback tự động mọi tình huống.

Project, ảnh, tiếng, font và bản sao lưu ở local; installer chỉ tải skill công khai. Skill không tải media lên dịch vụ riêng. File bạn đưa vào phiên Codex vẫn chịu cách xử lý dữ liệu của phiên đó.

## Giới hạn đã biết

### Đang phát triển trên main (chưa nằm trong installer v0.1.1)

- `probe` xử lý rõ đuôi video ngắn hơn audio/container dưới một frame, ghi timestamp mẫu thực tế và cảnh báo; không che một trim sai dài hơn bằng cách lặp hình. Xuất JPEG có pixel format tương thích.
- `restyle` giữ chữ, vị trí, timing, keyframe, hiệu ứng và các trường CapCut đã chuẩn hóa. Khi hash đã đổi, Codex phải đối chiếu bản nháp trước và ghi nhận xét với hash hiện tại; không cập nhật ownership trước khi ghi.
- Rà đủ nhân vật chính bằng `character_review`, hỗ trợ thẻ cho cặp nhân vật, ghi lý do cho từng người bỏ qua. Thẻ bối cảnh ưu tiên bám fade gốc; fade ngắn có thể nối chữ sang cảnh sau mà không kéo đen.
- Có thể tái dùng fade-in native đã có và đã được xác minh ở local, đồng bộ cả tên và vai trò; không tự tải hoặc bịa ID effect. `ending` dành cho chữ kết trên hình cuối có sẵn.
- Khi CapCut còn chạy nền, hướng dẫn lưu rồi thoát hẳn ứng dụng; trên macOS dùng Cmd+Q.

Xem [tham chiếu lệnh và plan](skills/capcut-cinematic-cards/references/tool.md). Các kiểm tra dữ liệu vẫn không xác nhận playback/render native CapCut.

### Bản đã phát hành

- Chỉ ghi draft JSON **không mã hóa, schema `360000`**. Định dạng khác sẽ dừng; không đổi schema bằng tay để vượt kiểm tra.
- Đường dẫn mặc định hỗ trợ tìm project macOS/Windows; có thể truyền đường dẫn chính xác. Mã xử lý file dùng Python đa nền tảng. Chạy file và media đã được kiểm tra trên macOS; chưa xác minh CapCut native trên Windows/Linux.
- Hỗ trợ map compound lồng, trim và tốc độ cố định. Reverse, loop, curve speed và compound ngoài chưa được map; Codex phải bỏ/defer vị trí thiếu bằng chứng.
- Khung hình trích từ nguồn **chưa compositing**. Crop, hiệu ứng, overlay, phụ đề và transition cần được đối chiếu từ draft; ảnh nguồn không chứng minh được kết quả cuối trong CapCut.
- Kiểm tra file thành công chứng minh dữ liệu gốc được giữ, **không chứng minh CapCut đã render/playback đúng**. Skill phải nói rõ trạng thái này. Không có renderer CapCut hoặc thao tác GUI đi kèm.

## Cho người phát triển

```bash
python3 -m unittest discover -s tests -v
```

30 test đã chạy đạt trên macOS, gồm trích hình/tiếng FFmpeg bằng media giả. Các test dùng project giả, không sửa phim thật: giữ compound/audio, mirror, tránh thoại, bằng chứng nhân vật, tùy chỉnh style, stale input, editor busy, apply/restore, ownership, installer và bảo vệ đường dẫn. CI chưa được bật; chưa tuyên bố đã chạy test trên Windows/Linux.

[Lệnh và schema plan](skills/capcut-cinematic-cards/references/tool.md) · [Nguyên tắc chọn card và style](skills/capcut-cinematic-cards/references/editing.md)

Thư mục cài có thể đổi bằng biến `CAPCUT_CARDS_SKILLS_DIR`. Installer giữ nguyên skill không thuộc quyền quản lý của nó. Bản sao skill cũ ở `capcut-cards-install-backups` bên cạnh thư mục `skills`. Muốn gỡ, bảo Codex gỡ riêng skill này; project và backup phim không nằm trong thư mục cài.
