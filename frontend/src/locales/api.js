import { apiLocale as en } from './en.js'
import { apiLocale as km } from './km.js'
export const apiCopy = {
  ko: {
    signup: '회원가입', signingUp: '가입 중…', loginLink: '로그인으로 돌아가기', confirmPassword: '비밀번호 확인', mismatch: '비밀번호가 일치하지 않습니다.', signupDuplicate: '이미 사용 중인 아이디입니다.', signupSuccess: '가입되었습니다. 로그인해주세요.', passwordFormat: '비밀번호는 앞뒤 공백 없이 72바이트 이내로 입력해주세요.', checking: '로그인 확인 중…', credentials: '아이디 또는 비밀번호를 확인해주세요.', required: '아이디와 비밀번호를 입력해주세요.',
    expired: '로그인이 만료되었습니다. 다시 로그인해주세요.', connection: '서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요.', timeout: '응답 시간이 초과되었습니다. 다시 시도해주세요.',
    invalid: '요청 내용을 확인해주세요. 질문은 2~500자로 입력해주세요.', unavailable: '답변을 준비하지 못했습니다. 잠시 후 다시 시도해주세요.', unexpected: '서버 응답을 확인하지 못했습니다. 다시 시도해주세요.',
    logoutFailed: '로그아웃하지 못했습니다. 다시 시도해주세요.', retry: '다시 시도', handoff: '담당자 확인이 필요합니다', noLink: '원문 링크가 제공되지 않았습니다.',
    chemical: '화학물질 안전', law: '중대재해 법령', lawQuestion: '중대재해처벌법에서 정한 중대산업재해 기준은 무엇인가요?', topics: '질문 영역',
    voiceInput: '음성 입력', listenAnswer: '답변 듣기', micDenied: '마이크 사용이 허용되지 않았습니다. 브라우저 설정에서 마이크를 허용해주세요.', voiceUnsupported: '이 브라우저에서는 녹음할 수 없습니다. 질문을 입력해주세요.',
    voiceFailed: '음성을 인식하지 못했습니다. 다시 말하거나 질문을 입력해주세요.', voiceEmpty: '말소리가 들리지 않았습니다. 마이크에 조금 더 가까이 말해주세요.', speakFailed: '답변을 재생하지 못했습니다. 화면에서 확인해주세요.', speechTail: '전체 경고와 출처는 화면에서 확인하세요.', voiceLanguage: '이 언어는 아직 음성 입력·듣기를 지원하지 않습니다. 글로 질문해주세요.',
  },
  zh: {
    signup: '注册', signingUp: '正在注册…', loginLink: '返回登录', confirmPassword: '确认密码', mismatch: '两次密码不一致。', signupDuplicate: '用户名已被使用。', signupSuccess: '注册成功，请登录。', passwordFormat: '密码不能有首尾空格，且不能超过72字节。', checking: '正在确认登录…', credentials: '请检查用户名或密码。', required: '请输入用户名和密码。', expired: '登录已过期，请重新登录。', connection: '无法连接服务器，请稍后重试。', timeout: '响应超时，请重试。',
    invalid: '请检查输入内容，问题需为2～500个字符。', unavailable: '暂时无法提供回答，请稍后重试。', unexpected: '无法确认服务器响应，请重试。', logoutFailed: '退出失败，请重试。', retry: '重试', handoff: '需要负责人确认', noLink: '未提供原文链接。',
    chemical: '化学品安全', law: '重大事故法规', lawQuestion: '重大事故处罚法中重大工业事故的标准是什么？', topics: '问题类别', voiceInput: '语音输入', listenAnswer: '收听回答', micDenied: '未允许使用麦克风。请在浏览器设置中允许麦克风。', voiceUnsupported: '此浏览器无法录音。请输入问题。', voiceFailed: '无法识别语音。请重试或输入问题。', voiceEmpty: '没有检测到声音。请靠近麦克风说话。', speakFailed: '无法播放回答。请在屏幕上查看。', speechTail: '完整警告和来源请在屏幕上确认。', voiceLanguage: '该语言暂不支持语音输入和收听，请用文字提问。',
  },
  vi: {
    signup: 'Đăng ký', signingUp: 'Đang đăng ký…', loginLink: 'Quay lại đăng nhập', confirmPassword: 'Xác nhận mật khẩu', mismatch: 'Mật khẩu không khớp.', signupDuplicate: 'Tên đăng nhập đã được sử dụng.', signupSuccess: 'Đăng ký thành công. Vui lòng đăng nhập.', passwordFormat: 'Mật khẩu không có khoảng trắng ở đầu/cuối và tối đa 72 byte.', checking: 'Đang kiểm tra đăng nhập…', credentials: 'Kiểm tra tên đăng nhập hoặc mật khẩu.', required: 'Nhập tên đăng nhập và mật khẩu.', expired: 'Phiên đã hết hạn. Vui lòng đăng nhập lại.', connection: 'Không thể kết nối máy chủ. Hãy thử lại sau.', timeout: 'Hết thời gian chờ. Vui lòng thử lại.',
    invalid: 'Kiểm tra nội dung. Câu hỏi cần từ 2 đến 500 ký tự.', unavailable: 'Chưa thể trả lời. Hãy thử lại sau.', unexpected: 'Không thể xác nhận phản hồi. Vui lòng thử lại.', logoutFailed: 'Chưa thể đăng xuất. Vui lòng thử lại.', retry: 'Thử lại', handoff: 'Cần người phụ trách xác nhận', noLink: 'Không có liên kết tài liệu gốc.',
    chemical: 'An toàn hóa chất', law: 'Luật tai nạn nghiêm trọng', lawQuestion: 'Tiêu chí tai nạn công nghiệp nghiêm trọng theo luật là gì?', topics: 'Loại câu hỏi', voiceInput: 'Nhập giọng nói', listenAnswer: 'Nghe trả lời', micDenied: 'Chưa cho phép dùng micro. Hãy cho phép micro trong cài đặt trình duyệt.', voiceUnsupported: 'Trình duyệt này không ghi âm được. Hãy nhập câu hỏi.', voiceFailed: 'Không nhận dạng được giọng nói. Hãy thử lại hoặc nhập câu hỏi.', voiceEmpty: 'Không nghe thấy giọng nói. Hãy nói gần micro hơn.', speakFailed: 'Không phát được câu trả lời. Hãy xem trên màn hình.', speechTail: 'Hãy xem toàn bộ cảnh báo và nguồn trên màn hình.', voiceLanguage: 'Ngôn ngữ này chưa hỗ trợ nhập và nghe giọng nói. Hãy nhập câu hỏi.',
  },
  en, km,
}
