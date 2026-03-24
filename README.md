# my-rpg
claude帮我做的小玩具
快说谢谢claude
移动端和桌面端存档不互通 需要导出桌面端JSON.stringify({
  s0: localStorage.getItem('wuji_sv_0'),
  s1: localStorage.getItem('wuji_sv_1'),
  s2: localStorage.getItem('wuji_sv_2')
})

并导入移动端
var d = JSON.parse('粘贴刚才的桌面端字符串');
if(d.s0) localStorage.setItem('wuji_sv_0', d.s0);
if(d.s1) localStorage.setItem('wuji_sv_1', d.s1);
if(d.s2) localStorage.setItem('wuji_sv_2', d.s2);

评价：罗德岛所需提示词文本量过大 不建议游玩现版本的开服时期罗德岛
克苏鲁世界观的总流程比较短 但是至少没ooc
