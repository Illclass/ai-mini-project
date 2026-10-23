// Suggestions are question prompts, never safety instructions or generated answers.
export const questionCopy = {
 ko: {
  generic:'화학물질', context:'{equipment}에서 {product}',
  primary:[ '{context} 작업 전에 어떤 안전 항목을 확인해야 하나요?', '{context} 취급에 맞는 장갑과 보안경은 어떻게 확인하나요?', '{context}의 보관 조건과 함께 두면 안 되는 물질은 어디서 확인하나요?', '{context} 작업 중 환기와 노출 상태는 어떻게 점검하나요?', '{context} 작업 후 잔여물과 오염 도구는 어떻게 정리하나요?', '{context} 누출·노출 사고 시 현장 비상 절차는 어디서 확인하나요?' ],
  detail:[ '{context} 작업 전 {detail} 관련 위험은 무엇을 확인해야 하나요?', '{context} 취급 시 {detail}에 대비한 보호구는 어떤 자료에서 확인하나요?', '{context} 보관 시 {detail} 관련 주의사항은 무엇인가요?', '{context} 작업 중 {detail} 징후가 보이면 어떤 절차를 확인해야 하나요?', '{context} 정리 시 {detail}와 관련된 잔류 위험은 어떻게 확인하나요?', '{context} 사고에서 {detail} 관련 응급조치 자료는 어디서 찾나요?' ],
  free:[ '{context}의 MSDS에서 어떤 항목부터 확인하나요?', '{context} 작업에서 {detail} 관련 주의사항을 알고 싶어요.' ],
 },
 zh: {
  generic:'化学品', context:'{equipment}中的{product}',
  primary:[ '{context}作业前应检查哪些安全项目？', '如何确认操作{context}所需的手套和护目镜？', '在哪里确认{context}的储存条件和不相容物质？', '操作{context}时如何检查通风和暴露情况？', '{context}作业后如何整理残留物和受污染工具？', '在哪里查阅{context}泄漏或暴露时的现场应急程序？' ],
  detail:[ '{context}作业前应核查哪些与{detail}有关的风险？', '操作{context}时，应在哪里确认针对{detail}的防护用品？', '储存{context}时，与{detail}有关的注意事项是什么？', '操作{context}时出现{detail}迹象，应查阅什么程序？', '清理{context}时，如何确认与{detail}有关的残留风险？', '发生{context}事故时，在哪里查阅与{detail}有关的急救资料？' ],
  free:[ '应先查看{context}安全数据表中的哪些项目？', '我想了解{context}作业中与{detail}有关的注意事项。' ],
 },
 vi: {
  generic:'hóa chất', context:'{product} tại {equipment}',
  primary:[ 'Cần kiểm tra những mục an toàn nào trước khi làm việc với {context}?', 'Làm sao xác nhận găng tay và kính bảo hộ khi thao tác với {context}?', 'Xem điều kiện bảo quản và các chất không tương thích với {context} ở đâu?', 'Kiểm tra thông gió và phơi nhiễm khi làm việc với {context} thế nào?', 'Sau khi làm việc với {context}, dọn hóa chất dư và dụng cụ nhiễm bẩn thế nào?', 'Xem quy trình khẩn cấp tại chỗ khi rò rỉ hoặc phơi nhiễm {context} ở đâu?' ],
  detail:[ 'Trước khi dùng {context}, cần kiểm tra gì về nguy cơ {detail}?', 'Xem tài liệu nào để chọn bảo hộ cho nguy cơ {detail} khi dùng {context}?', 'Khi bảo quản {context}, cần lưu ý gì về {detail}?', 'Khi làm việc với {context} có dấu hiệu {detail}, cần xem quy trình nào?', 'Khi dọn dẹp {context}, kiểm tra nguy cơ tồn dư liên quan đến {detail} thế nào?', 'Tìm tài liệu sơ cứu về {detail} trong sự cố {context} ở đâu?' ],
  free:[ 'Nên xem mục nào trước trong MSDS của {context}?', 'Tôi muốn biết lưu ý về {detail} khi làm việc với {context}.' ],
 },
 en: {
  generic:'chemicals', context:'{product} on {equipment}',
  primary:[ 'What safety checks are needed before working with {context}?', 'How do I check which gloves and goggles are appropriate for {context}?', 'Where can I check storage conditions and incompatible materials for {context}?', 'How do I check ventilation and exposure during work with {context}?', 'How should I check cleanup procedures for residues and contaminated tools after using {context}?', 'Where can I find site emergency procedures for a spill or exposure involving {context}?' ],
  detail:[ 'What risks related to {detail} should I check before working with {context}?', 'Which documents identify PPE for {detail} when handling {context}?', 'What precautions related to {detail} apply when storing {context}?', 'Which procedures should I check if I notice {detail} during work with {context}?', 'How do I check residual risks related to {detail} when cleaning up {context}?', 'Where can I find first-aid documentation for {detail} in an incident involving {context}?' ],
  free:[ 'Which MSDS sections should I read first for {context}?', 'What precautions should I check for {detail} when working with {context}?' ],
 },
 km: {
  generic:'សារធាតុគីមី', context:'{product} នៅ {equipment}',
  primary:[ 'តើត្រូវពិនិត្យសុវត្ថិភាពអ្វីខ្លះ មុនធ្វើការជាមួយ {context}?', 'តើពិនិត្យស្រោមដៃ និងវ៉ែនតាការពារសម្រាប់ {context} យ៉ាងដូចម្តេច?', 'តើរកលក្ខខណ្ឌផ្ទុក និងសារធាតុមិនត្រូវគ្នាជាមួយ {context} នៅឯណា?', 'តើពិនិត្យខ្យល់ចេញចូល និងការប៉ះពាល់ ពេលធ្វើការជាមួយ {context} យ៉ាងដូចម្តេច?', 'តើពិនិត្យការសម្អាតសំណល់ និងឧបករណ៍កខ្វក់ ក្រោយប្រើ {context} យ៉ាងដូចម្តេច?', 'តើរកនីតិវិធីបន្ទាន់នៅកន្លែងធ្វើការ សម្រាប់ការលេចធ្លាយ ឬការប៉ះពាល់ {context} នៅឯណា?' ],
  detail:[ 'មុនប្រើ {context} តើត្រូវពិនិត្យហានិភ័យទាក់ទងនឹង {detail} អ្វីខ្លះ?', 'តើឯកសារណាបញ្ជាក់ឧបករណ៍ការពារ {detail} ពេលប្រើ {context}?', 'ពេលផ្ទុក {context} តើមានការប្រុងប្រយ័ត្នអ្វីចំពោះ {detail}?', 'ពេលប្រើ {context} មានសញ្ញា {detail} តើត្រូវពិនិត្យនីតិវិធីណា?', 'ពេលសម្អាត {context} តើពិនិត្យហានិភ័យសំណល់ទាក់ទងនឹង {detail} យ៉ាងដូចម្តេច?', 'តើរកឯកសារសង្គ្រោះបឋមសម្រាប់ {detail} ក្នុងហេតុការណ៍ {context} នៅឯណា?' ],
  free:[ 'តើគួរអានផ្នែកណាខ្លះនៃ MSDS សម្រាប់ {context} ជាមុន?', 'តើត្រូវប្រុងប្រយ័ត្នអ្វីចំពោះ {detail} ពេលប្រើ {context}?' ],
 },
}
// Ordered ko, zh, vi, en, km. These describe question themes, not risk classifications.
export const productThemes = {
 'sigma-339741':['희석 시 비산','稀释时飞溅','bắn tóe khi pha loãng','splashes during dilution','ការខ្ទាតពេលពង្រាវ'],
 'sigma-695068':['불산 접촉','氢氟酸接触','tiếp xúc axit hydrofluoric','hydrofluoric acid contact','ការប៉ះអាស៊ីតអ៊ីដ្រូហ្វ្លុយអរីក'],
 'merck-8.22287':['분해와 용기 압력','分解与容器压力','phân hủy và áp suất bình chứa','decomposition and container pressure','ការបំបែក និងសម្ពាធធុង'],
 'sigma-221228':['암모니아 증기','氨蒸气','hơi amoniac','ammonia vapor','ចំហាយអាម៉ូញាក់'],
 'sigma-258148':['염화수소 증기','氯化氢蒸气','hơi hydro clorua','hydrogen chloride vapor','ចំហាយអ៊ីដ្រូសែនក្លរួ'],
 'sigma-438073':['산화성 물질 접촉','氧化性物质接触','tiếp xúc chất oxy hóa','contact with oxidizing materials','ការប៉ះសារធាតុអុកស៊ីតកម្ម'],
 'merck-1.00573':['산성 약액 비산','酸液飞溅','bắn tóe dung dịch axit','acid solution splashes','ការខ្ទាតទឹកអាស៊ីត'],
 'sigma-328251':['TMAH 피부 접촉','TMAH皮肤接触','TMAH tiếp xúc da','TMAH skin contact','TMAH ប៉ះស្បែក'],
 'sigma-179124':['용제 증기와 점화원','溶剂蒸气与点火源','hơi dung môi và nguồn cháy','solvent vapor and ignition sources','ចំហាយសារធាតុរំលាយ និងប្រភពបញ្ឆេះ'],
 'sigma-34860':['메탄올 노출','甲醇暴露','phơi nhiễm metanol','methanol exposure','ការប៉ះពាល់មេតាណុល'],
 'sigma-563935':['IPA 증기와 정전기','IPA蒸气与静电','hơi IPA và tĩnh điện','IPA vapor and static electricity','ចំហាយ IPA និងអគ្គិសនីឋិតិវន្ត'],
 'sigma-484431':['PGMEA 증기','PGMEA蒸气','hơi PGMEA','PGMEA vapor','ចំហាយ PGMEA'],
 'sigma-221465':['알칼리 약액 접촉','碱液接触','tiếp xúc dung dịch kiềm','alkaline solution contact','ការប៉ះទឹកអាល់កាឡាំង'],
}
export const equipmentThemes = {
 cleaning:['약액 교체','更换药液','thay dung dịch','chemical bath replacement','ការប្តូរទឹកគីមី'],
 photo:['현상액 공급라인','显影液供应管线','đường cấp dung dịch hiện ảnh','developer supply lines','បំពង់ផ្គត់ផ្គង់សារធាតុបង្កើតរូប'],
 etch_wet:['식각조 개방','打开蚀刻槽','mở bể khắc','opening an etch bath','ការបើកធុងឆ្លាក់'],
 cmp:['슬러리 공급라인','研磨液供应管线','đường cấp dung dịch đánh bóng','slurry supply lines','បំពង់ផ្គត់ផ្គង់ស្លារី'],
 solvent:['용제 세척과 유지보수','溶剂清洗与维护','vệ sinh và bảo trì bằng dung môi','solvent cleaning and maintenance','ការសម្អាត និងថែទាំដោយសារធាតុរំលាយ'],
 utility:['폐수 중화와 배기','废水中和与排气','trung hòa nước thải và khí thải','wastewater neutralization and exhaust','ការបន្សាបទឹកកខ្វក់ និងខ្យល់ចេញ'],
}
export const genericThemes = ['누출과 오염','泄漏与污染','rò rỉ và nhiễm bẩn','leaks and contamination','ការលេចធ្លាយ និងការបំពុល']
