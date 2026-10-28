// Province names are navigation hints; weather is always requested for a specific city.
export type CityHint = { name: string; query: string }
export type ProvinceHint = { name: string; cities: CityHint[] }
const capital = (name: string, city: string, query: string): ProvinceHint => ({ name, cities: [{ name: city, query }] })
export const chinaProvinces: ProvinceHint[] = [
  capital('北京', '北京', 'Beijing'), capital('天津', '天津', 'Tianjin'), capital('上海', '上海', 'Shanghai'), capital('重庆', '重庆', 'Chongqing'),
  capital('河北', '石家庄', 'Shijiazhuang'), capital('山西', '太原', 'Taiyuan'), capital('辽宁', '沈阳', 'Shenyang'), capital('吉林', '长春', 'Changchun'), capital('黑龙江', '哈尔滨', 'Harbin'),
  capital('江苏', '南京', 'Nanjing'), capital('浙江', '杭州', 'Hangzhou'), capital('安徽', '合肥', 'Hefei'), capital('福建', '福州', 'Fuzhou'), capital('江西', '南昌', 'Nanchang'), capital('山东', '济南', 'Jinan'), capital('河南', '郑州', 'Zhengzhou'),
  { name: '湖北', cities: [
    ['武汉', 'Wuhan'], ['黄石', 'Huangshi'], ['十堰', 'Shiyan'], ['宜昌', 'Yichang'], ['襄阳', 'Xiangyang'], ['鄂州', 'Ezhou'], ['荆门', 'Jingmen'], ['孝感', 'Xiaogan'], ['荆州', 'Jingzhou'], ['黄冈', 'Huanggang'], ['咸宁', 'Xianning'], ['随州', 'Suizhou'], ['恩施', 'Enshi'], ['仙桃', 'Xiantao'], ['潜江', 'Qianjiang'], ['天门', 'Tianmen'], ['神农架', 'Shennongjia'],
  ].map(([name, query]) => ({ name: name!, query: query! })) },
  capital('湖南', '长沙', 'Changsha'), capital('广东', '广州', 'Guangzhou'), capital('海南', '海口', 'Haikou'), capital('四川', '成都', 'Chengdu'), capital('贵州', '贵阳', 'Guiyang'), capital('云南', '昆明', 'Kunming'), capital('陕西', '西安', 'Xian'), capital('甘肃', '兰州', 'Lanzhou'), capital('青海', '西宁', 'Xining'),
  capital('内蒙古', '呼和浩特', 'Hohhot'), capital('广西', '南宁', 'Nanning'), capital('西藏', '拉萨', 'Lhasa'), capital('宁夏', '银川', 'Yinchuan'), capital('新疆', '乌鲁木齐', 'Urumqi'), capital('香港', '香港', 'Hong Kong'), capital('澳门', '澳门', 'Macao'), capital('台湾', '台北', 'Taipei'),
]
export const normalizeRegion = (value: string) => value.trim().replace(/(特别行政区|维吾尔自治区|壮族自治区|回族自治区|自治区|省|市)$/, '')
export const findProvince = (value: string) => chinaProvinces.find(province => province.name === normalizeRegion(value))
