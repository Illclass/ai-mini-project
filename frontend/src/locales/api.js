import { apiLocale as en } from './en.js'
import { apiLocale as km } from './km.js'
export const apiCopy = {
  ko: {
    signup: '회원가입', signingUp: '가입 중…', loginLink: '로그인으로 돌아가기', confirmPassword: '비밀번호 확인', mismatch: '비밀번호가 일치하지 않습니다.', signupDuplicate: '이미 사용 중인 아이디입니다.', signupSuccess: '가입되었습니다. 로그인해주세요.', passwordFormat: '비밀번호는 앞뒤 공백 없이 72바이트 이내로 입력해주세요.', checking: '로그인 확인 중…', credentials: '아이디 또는 비밀번호를 확인해주세요.', required: '아이디와 비밀번호를 입력해주세요.',
    expired: '로그인이 만료되었습니다. 다시 로그인해주세요.', connection: '서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요.', timeout: '응답 시간이 초과되었습니다. 다시 시도해주세요.',
    invalid: '요청 내용을 확인해주세요. 질문은 2~500자로 입력해주세요.', unavailable: '답변을 준비하지 못했습니다. 잠시 후 다시 시도해주세요.', unexpected: '서버 응답을 확인하지 못했습니다. 다시 시도해주세요.',
    logoutFailed: '로그아웃하지 못했습니다. 다시 시도해주세요.', retry: '다시 시도', handoff: '담당자 확인이 필요합니다', answerNote: '자료 기반 참고용 안내 · 현장 적용 전 담당자 확인', noLink: '원문 링크가 제공되지 않았습니다.',
    chemical: '화학물질 안전', law: '중대재해 법령', lawQuestion: '중대재해처벌법에서 정한 중대산업재해 기준은 무엇인가요?', topics: '질문 영역',
    voicePreview: '음성 입력 · 미리보기', listenPreview: '답변 듣기 · 미리보기',
  },
  zh: {
    signup: '注册', signingUp: '正在注册…', loginLink: '返回登录', confirmPassword: '确认密码', mismatch: '两次密码不一致。', signupDuplicate: '用户名已被使用。', signupSuccess: '注册成功，请登录。', passwordFormat: '密码不能有首尾空格，且不能超过72字节。', checking: '正在确认登录…', credentials: '请检查用户名或密码。', required: '请输入用户名和密码。', expired: '登录已过期，请重新登录。', connection: '无法连接服务器，请稍后重试。', timeout: '响应超时，请重试。',
    invalid: '请检查输入内容，问题需为2～500个字符。', unavailable: '暂时无法提供回答，请稍后重试。', unexpected: '无法确认服务器响应，请重试。', logoutFailed: '退出失败，请重试。', retry: '重试', handoff: '需要负责人确认', answerNote: '基于资料的参考信息 · 现场使用前请向负责人确认', noLink: '未提供原文链接。',
    chemical: '化学品安全', law: '重大事故法规', lawQuestion: '重大事故处罚法中重大工业事故的标准是什么？', topics: '问题类别', voicePreview: '语音输入 · 预览', listenPreview: '收听回答 · 预览',
  },
  vi: {
    signup: 'Đăng ký', signingUp: 'Đang đăng ký…', loginLink: 'Quay lại đăng nhập', confirmPassword: 'Xác nhận mật khẩu', mismatch: 'Mật khẩu không khớp.', signupDuplicate: 'Tên đăng nhập đã được sử dụng.', signupSuccess: 'Đăng ký thành công. Vui lòng đăng nhập.', passwordFormat: 'Mật khẩu không có khoảng trắng ở đầu/cuối và tối đa 72 byte.', checking: 'Đang kiểm tra đăng nhập…', credentials: 'Kiểm tra tên đăng nhập hoặc mật khẩu.', required: 'Nhập tên đăng nhập và mật khẩu.', expired: 'Phiên đã hết hạn. Vui lòng đăng nhập lại.', connection: 'Không thể kết nối máy chủ. Hãy thử lại sau.', timeout: 'Hết thời gian chờ. Vui lòng thử lại.',
    invalid: 'Kiểm tra nội dung. Câu hỏi cần từ 2 đến 500 ký tự.', unavailable: 'Chưa thể trả lời. Hãy thử lại sau.', unexpected: 'Không thể xác nhận phản hồi. Vui lòng thử lại.', logoutFailed: 'Chưa thể đăng xuất. Vui lòng thử lại.', retry: 'Thử lại', handoff: 'Cần người phụ trách xác nhận', answerNote: 'Thông tin tham khảo từ tài liệu · Xác nhận với người phụ trách trước khi áp dụng', noLink: 'Không có liên kết tài liệu gốc.',
    chemical: 'An toàn hóa chất', law: 'Luật tai nạn nghiêm trọng', lawQuestion: 'Tiêu chí tai nạn công nghiệp nghiêm trọng theo luật là gì?', topics: 'Loại câu hỏi', voicePreview: 'Nhập giọng nói · xem trước', listenPreview: 'Nghe trả lời · xem trước',
  },
  en, km,
}

// Diagnostic messages are UI copy, not model-generated answers/translations.
const diagnosticCopy = {
 ko: {
  providerErrorTitle:'AI 제공자 연결 오류', providerError:'AI 제공자 호출을 완료하지 못했습니다. 운영 담당자가 제공자 상태와 설정을 확인해야 합니다.',
  providerLimitedTitle:'AI 제공자가 요청을 제한했습니다', providerLimited:'AI 제공자가 요청을 제한했습니다(429). 크레딧·사용 한도·요청 제한 중 원인은 기관 담당자의 확인이 필요합니다.',
  experimentStoppedTitle:'실험 호출이 중단되어 있습니다', experimentStopped:'이전 제공자 오류 이후 실험 호출이 중단되어 있습니다. 이번 요청은 AI 제공자에게 전송하지 않았습니다. 운영 담당자의 확인 후 검사를 재개해야 합니다.',
  experimentScopeTitle:'승인된 실험 범위 밖입니다', experimentScope:'현재 승인된 질문·자료·호출 범위에 포함되지 않아 전송을 중단했습니다. 운영 담당자에게 실험 범위를 확인해 주세요.',
  evidenceFailedTitle:'근거 검증으로 답변을 보류했습니다', evidenceFailed:'생성한 답변의 인용·내용·번역 또는 검색 자료의 조건을 검증하지 못했습니다. 검증되지 않은 답변은 제공하지 않습니다.',
  verificationUnavailableTitle:'근거 검증을 완료하지 못했습니다', verificationUnavailable:'검증 처리를 완료하지 못해 답변을 보류했습니다. 자료가 없다고 확인된 것은 아닙니다. 운영 담당자가 검증 상태를 확인해야 합니다.',
  evidenceMissingTitle:'답변할 근거가 부족합니다', evidenceMissing:'제공된 검색 자료만으로는 질문에 답할 충분한 근거를 확인하지 못했습니다. 관련 자료를 확보하거나 질문 범위를 확인해 주세요.',
  productUnverifiedTitle:'제품 정보 확인이 필요합니다', productUnverified:'선택한 제품과 검색된 MSDS의 제품명·제품번호·농도·개정일을 확인하지 못했습니다. 제품 선택과 원문 자료를 확인해 주세요.',
  generationErrorTitle:'답변 생성 처리 오류', generationError:'답변 생성 처리를 완료하지 못했습니다. 문의용 오류 번호와 함께 운영 담당자에게 알려주세요.',
  errorReference:'문의용 오류 번호',
 },
 zh: {
  providerErrorTitle:'AI 服务调用失败', providerError:'未能完成 AI 服务调用。请运营负责人检查服务状态和配置。',
  providerLimitedTitle:'AI 服务限制了请求', providerLimited:'AI 服务限制了请求（429）。请机构负责人检查余额、使用额度和请求速率限制。',
  experimentStoppedTitle:'实验调用已暂停', experimentStopped:'此前 AI 服务出错后，实验调用已暂停。本次请求未发送给 AI 服务。需经运营负责人确认后恢复测试。',
  experimentScopeTitle:'超出已批准的实验范围', experimentScope:'问题、资料或调用超出了已批准范围，因此未发送。请向运营负责人确认实验范围。',
  evidenceFailedTitle:'依据验证未通过，暂不提供回答', evidenceFailed:'未能验证回答的引用、内容、翻译或检索资料的适用条件。不会提供未经验证的回答。',
  verificationUnavailableTitle:'未能完成依据验证', verificationUnavailable:'验证未完成，因此暂不提供回答。这不表示没有资料。请运营负责人检查验证状态。',
  evidenceMissingTitle:'回答依据不足', evidenceMissing:'现有检索资料不足以回答该问题。请补充相关资料或确认问题范围。',
  productUnverifiedTitle:'需要核实产品信息', productUnverified:'未能核实所选产品与 MSDS 中的产品名、编号、浓度和修订日期。请检查产品选择和原文。',
  generationErrorTitle:'回答生成处理出错', generationError:'未能完成回答生成。请将错误编号提供给运营负责人。',
  errorReference:'错误查询编号',
 },
 vi: {
  providerErrorTitle:'Lỗi gọi dịch vụ AI', providerError:'Không thể hoàn tất lệnh gọi AI. Người vận hành cần kiểm tra trạng thái và cấu hình dịch vụ.',
  providerLimitedTitle:'Dịch vụ AI đã giới hạn yêu cầu', providerLimited:'Dịch vụ AI đã giới hạn yêu cầu (429). Đơn vị quản lý cần kiểm tra số dư, hạn mức sử dụng và giới hạn tốc độ yêu cầu.',
  experimentStoppedTitle:'Các lệnh gọi thử nghiệm đã tạm dừng', experimentStopped:'Các lệnh gọi thử nghiệm đã dừng sau lỗi dịch vụ AI trước đó. Yêu cầu này chưa được gửi đến AI. Chỉ tiếp tục sau khi người vận hành xác nhận.',
  experimentScopeTitle:'Ngoài phạm vi thử nghiệm được duyệt', experimentScope:'Câu hỏi, tài liệu hoặc lệnh gọi nằm ngoài phạm vi được duyệt nên chưa được gửi. Hãy xác nhận phạm vi với người vận hành.',
  evidenceFailedTitle:'Tạm hoãn trả lời do kiểm chứng căn cứ', evidenceFailed:'Chưa kiểm chứng được trích dẫn, nội dung, bản dịch hoặc điều kiện áp dụng của tài liệu. Không cung cấp câu trả lời chưa được kiểm chứng.',
  verificationUnavailableTitle:'Chưa hoàn tất kiểm chứng căn cứ', verificationUnavailable:'Tạm hoãn trả lời vì chưa hoàn tất kiểm chứng. Điều này không có nghĩa là không có tài liệu. Người vận hành cần kiểm tra trạng thái kiểm chứng.',
  evidenceMissingTitle:'Chưa đủ căn cứ để trả lời', evidenceMissing:'Tài liệu tìm được chưa đủ để trả lời. Hãy bổ sung tài liệu liên quan hoặc xác nhận phạm vi câu hỏi.',
  productUnverifiedTitle:'Cần xác nhận thông tin sản phẩm', productUnverified:'Chưa xác nhận được tên, mã sản phẩm, nồng độ và ngày sửa đổi giữa sản phẩm đã chọn và MSDS. Hãy kiểm tra lựa chọn và tài liệu gốc.',
  generationErrorTitle:'Lỗi xử lý tạo câu trả lời', generationError:'Không thể hoàn tất việc tạo câu trả lời. Hãy gửi mã lỗi cho người vận hành.',
  errorReference:'Mã tra cứu lỗi',
 },
 en: {
  providerErrorTitle:'AI provider error', providerError:'The AI provider call could not be completed. An operator needs to check provider status and configuration.',
  providerLimitedTitle:'The AI provider limited the request', providerLimited:'The AI provider limited the request (429). The institution needs to check credits, usage limits and request rate limits.',
  experimentStoppedTitle:'Experiment calls are paused', experimentStopped:'Experiment calls remain paused after an earlier provider error. This request was not sent to the AI provider. An operator must confirm before testing resumes.',
  experimentScopeTitle:'Outside the approved experiment scope', experimentScope:'The question, documents or call fall outside the approved scope, so transmission was stopped. Check the scope with an operator.',
  evidenceFailedTitle:'Answer withheld by evidence verification', evidenceFailed:'The answer citations, content, translation or source conditions could not be verified. An unverified answer will not be provided.',
  verificationUnavailableTitle:'Evidence verification could not finish', verificationUnavailable:'The answer was withheld because verification did not finish. This does not establish that documents are missing. An operator needs to check verification status.',
  evidenceMissingTitle:'Insufficient evidence to answer', evidenceMissing:'The retrieved documents do not provide enough evidence to answer. Obtain relevant documents or check the question scope.',
  productUnverifiedTitle:'Product details need confirmation', productUnverified:'The selected product could not be matched to the MSDS product name, number, concentration and revision date. Check the selection and original document.',
  generationErrorTitle:'Answer processing error', generationError:'Answer generation could not be completed. Share the error reference with an operator.',
  errorReference:'Error reference',
 },
 km: {
  providerErrorTitle:'កំហុសសេវា AI', providerError:'មិនអាចបញ្ចប់ការហៅសេវា AI បានទេ។ អ្នកគ្រប់គ្រងត្រូវពិនិត្យស្ថានភាព និងការកំណត់សេវា។',
  providerLimitedTitle:'សេវា AI បានកំណត់សំណើ', providerLimited:'សេវា AI បានកំណត់សំណើ (429)។ ស្ថាប័នត្រូវពិនិត្យឥណទាន កម្រិតប្រើប្រាស់ និងអត្រាសំណើ។',
  experimentStoppedTitle:'ការហៅសាកល្បងត្រូវបានផ្អាក', experimentStopped:'ការហៅសាកល្បងនៅតែផ្អាកបន្ទាប់ពីកំហុសសេវា AI មុននេះ។ សំណើនេះមិនត្រូវបានផ្ញើទៅ AI ទេ។ ត្រូវឱ្យអ្នកគ្រប់គ្រងបញ្ជាក់មុនបន្តសាកល្បង។',
  experimentScopeTitle:'នៅក្រៅវិសាលភាពសាកល្បងដែលបានអនុម័ត', experimentScope:'សំណួរ ឯកសារ ឬការហៅស្ថិតនៅក្រៅវិសាលភាពដែលបានអនុម័ត ដូច្នេះមិនបានផ្ញើទេ។ សូមពិនិត្យវិសាលភាពជាមួយអ្នកគ្រប់គ្រង។',
  evidenceFailedTitle:'ផ្អាកចម្លើយដោយសារការផ្ទៀងផ្ទាត់ភស្តុតាង', evidenceFailed:'មិនអាចផ្ទៀងផ្ទាត់សម្រង់ ខ្លឹមសារ ការបកប្រែ ឬលក្ខខណ្ឌឯកសារបានទេ។ មិនផ្តល់ចម្លើយដែលមិនបានផ្ទៀងផ្ទាត់ឡើយ។',
  verificationUnavailableTitle:'មិនអាចបញ្ចប់ការផ្ទៀងផ្ទាត់ភស្តុតាង', verificationUnavailable:'ចម្លើយត្រូវបានផ្អាកព្រោះការផ្ទៀងផ្ទាត់មិនទាន់បញ្ចប់។ នេះមិនមានន័យថាគ្មានឯកសារទេ។ អ្នកគ្រប់គ្រងត្រូវពិនិត្យស្ថានភាព។',
  evidenceMissingTitle:'ភស្តុតាងមិនគ្រប់គ្រាន់សម្រាប់ឆ្លើយ', evidenceMissing:'ឯកសារដែលស្វែងរកបានមិនមានភស្តុតាងគ្រប់គ្រាន់ទេ។ សូមបន្ថែមឯកសារពាក់ព័ន្ធ ឬពិនិត្យវិសាលភាពសំណួរ។',
  productUnverifiedTitle:'ត្រូវបញ្ជាក់ព័ត៌មានផលិតផល', productUnverified:'មិនអាចផ្ទៀងផ្ទាត់ឈ្មោះ លេខផលិតផល កំហាប់ និងកាលបរិច្ឆេទកែប្រែជាមួយ MSDS បានទេ។ សូមពិនិត្យជម្រើសផលិតផល និងឯកសារដើម។',
  generationErrorTitle:'កំហុសក្នុងការបង្កើតចម្លើយ', generationError:'មិនអាចបញ្ចប់ការបង្កើតចម្លើយបានទេ។ សូមផ្តល់លេខយោងកំហុសដល់អ្នកគ្រប់គ្រង។',
  errorReference:'លេខយោងកំហុស',
 },
}
for(const [language,fields] of Object.entries(diagnosticCopy))Object.assign(apiCopy[language],fields)
