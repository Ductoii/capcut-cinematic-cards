# CapCut Harness + Cinematic Cards

**UI local để cân âm thoại cả phim, nghe A/B và Apply/Undo; kèm skill thêm time, location và giới thiệu nhân vật có tên + vai trò.**

[English](README.en.md) · [Bản phát hành v0.2.0](https://github.com/Ductoii/capcut-cinematic-cards/releases/tag/v0.2.0) · [Bằng chứng kiểm thử](docs/verification.md) · [MIT](LICENSE)

Media ở trên máy. Không cần Computer Use, API key hay tài khoản dịch vụ âm thanh. Nút bấm và ô lệnh gọi cùng một harness; ô lệnh nhận một tập câu xác định, không phải chatbot tự do. Codex hiện tại làm phần quyết định biên tập khi đặt card.

## Cài harness một dòng

Trên **macOS**, chuẩn bị **Python 3.10–3.13, FFmpeg và ffprobe** trên PATH. Bộ cài cài NumPy/ONNX Runtime trong môi trường riêng, không sửa Python chung. macOS là nền tảng đã kiểm thử; Linux/Windows chưa được xác minh đầy đủ.

```bash
curl -fsSL https://raw.githubusercontent.com/Ductoii/capcut-cinematic-cards/v0.2.0/install-harness.py | python3
```

Nếu không rành Terminal, gửi link repo cho **Codex local trên máy có project** và nói:

> Cài CapCut Harness v0.2.0, chuẩn bị dependency còn thiếu rồi mở UI local giúp tôi. Không computer use.

Bộ cài lấy đúng tag v0.2.0, tạo môi trường riêng và cài **hai skill** vào `~/.agents/skills`. Chạy lại cùng lệnh sẽ giữ release cũ và sao lưu skill/launcher; thư mục không do bộ cài quản lý được giữ nguyên. Không clone repo, không sửa JSON. Nếu Codex chưa thấy skill mới, khởi động lại Codex.

Mở UI bằng:

```bash
~/.local/bin/capcut-harness
```

Giữ Terminal đang chạy. Trình duyệt mở địa chỉ `127.0.0.1` trên chính máy đó; chạy lại lệnh sẽ mở service đang chạy. `Ctrl+C` dừng an toàn. Mở lại lệnh để xem các công việc đã lưu. Không xóa `~/.local/share/capcut-harness`: đó là nơi chứa bản nghe, báo cáo và backup phục vụ Undo. Có thể tốn vài GB cho một phim dài.

## Cân thoại bằng UI

1. Chọn project ở thanh trên. Nếu chưa thấy, chọn **Thêm project** và gửi đường dẫn thư mục project CapCut; có thể nhờ Codex tìm đúng thư mục giúp.
2. Bấm **Cân âm thoại**. Việc này đọc timeline và media, nhận diện giọng nói, đo từng khoảng rồi tạo bản nghe. Project chưa thay đổi. Có tiến độ, hủy và thử lại khi lỗi/gián đoạn.
3. Xem độ chênh P10–P90, trung vị thoại và peak thực. Chọn một khoảng trong bảng để nghe; nút **Bản gốc / Sau xử lý** giữ cùng vị trí nghe.
4. Bỏ chọn khoảng nhận nhầm hoặc đổi mục tiêu/mức tăng/trần peak rồi bấm **Cập nhật bản nghe**. Chỉ revision hiện tại được Apply; bản cũ vẫn nằm trong **Công việc**.
5. Nghe và duyệt bản xử lý. **Lưu rồi đóng CapCut**; bấm **Áp dụng vào project**. Harness thêm một track master audio ở ngoài clip ghép, tắt âm các đoạn gốc đang nghe được để tránh phát trùng. Giữ nguyên cấu trúc hình, clip ghép và text card.
6. Mở lại CapCut để kiểm tra nghe/xem thực tế. Muốn trở về: lưu, đóng CapCut và bấm **Hoàn tác** ở đúng công việc đã Apply. Nếu project đã thay đổi, công cụ dừng để giữ chỉnh sửa của bạn; nhờ Codex đối chiếu backup, đừng ghi đè draft thủ công.

Mặc định: thoại −18 LUFS, tăng/giảm tối đa 12 dB, peak toàn master tối đa −1,5 dBTP, stereo 48 kHz PCM24. Phép đo sau xử lý quyết định kết quả; đoạn chưa đạt được báo riêng. Gain bằng 0 ở đoạn bỏ chọn; limiter cuối vẫn bảo vệ peak toàn master.

**Giới hạn âm thanh:** VAD nhận diện giọng nói, không tách nhạc, không đoán nhân vật và không dịch/chép thoại. Nhạc/SFX dính vào giọng sẽ đổi mức cùng đoạn đó. Hát, thoại quá ngắn/nhiễu có thể bị nhận nhầm; cần nghe A/B và bỏ chọn khi cần. Luồng này cân mức giữa các câu, không thay diễn xuất trong câu bằng một mức phẳng.

**Tương thích hiện tại:** JSON CapCut local đọc được, không mã hóa, schema `360000`, đã kiểm thử trên macOS. Công cụ dừng với hiệu ứng âm thanh, routing, tốc độ biến thiên hoặc cờ mute chưa hiểu. Bản mix dựng lại từ nguồn chưa được coi là native render CapCut; báo cáo giữ `editor_render_verified: false`. Không đảm bảo mọi phiên bản/project CapCut đều dùng được.

## Ra lệnh qua Codex hoặc ô lệnh

```text
$capcut-harness
Cân âm thoại project 1027, cho tôi nghe A/B và xem đoạn nào còn lệch.
Giữ nguyên hình, clip ghép và card.
```

Các câu được hỗ trợ: `phân tích <project>`, `cân âm thoại <project>`, `áp dụng <job>`, `hoàn tác <job>`, `thử lại <job>`. Tên trùng phải chọn project trong UI. Câu chưa hỗ trợ không chạy gì. Tab **Cinematic cards** liệt kê text đang có; việc phân tích nhân vật/đặt card dùng skill ở phần dưới.

CLI dành cho Codex: `capcut-harness --help`, `capcut-harness inspect /path/to/project`, `capcut-harness command "cân âm thoại Tên phim"`. CLI chờ kết quả và dùng chung service khi UI đang mở. [Hướng dẫn kỹ thuật](docs/harness-development.md).

## Cinematic cards độc lập

Phần dưới là hướng dẫn đầy đủ cho công cụ card; lệnh cài v0.1.1 chỉ cài skill card, không cài harness/audio. Bộ cài harness v0.2.0 ở trên đã bao gồm skill này.


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
