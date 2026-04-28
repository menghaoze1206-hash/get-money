const api = require('../../utils/api');

Page({
  data: {
    signal: 'hold',
    signalText: '加载中…',
    signalDesc: '',
    currentYield: '--',
    bondYield: '--',
    riskPremium: '--',
    histAvgYield: '--',
    verdictText: '',
    updateTime: ''
  },

  onLoad() {
    this.fetchData();
  },

  onPullDownRefresh() {
    this.fetchData().then(() => wx.stopPullDownRefresh());
  },

  async fetchData() {
    try {
      const data = await api.request('/api/dividend');
      const currentYield = Number(data.current_yield || 0);
      const bondYield = Number(data.bond_yield_10y || 0);
      const histAvgYield = Number(data.hist_yield_avg_1y || 0);
      const riskPremium = currentYield - bondYield;
      const histSpread = histAvgYield - bondYield;

      let signal = 'hold';
      let signalText = '';
      let signalDesc = '';
      let verdictText = '';

      if (riskPremium >= 3.0 && currentYield >= histAvgYield * 1.1) {
        signal = 'buy';
        signalText = '当前宜投';
        signalDesc = '股息率显著高于国债收益率，红利基金具备较高配置价值';
        verdictText = `当前股息率 ${currentYield.toFixed(2)}% 远高于 10 年期国债收益率 ${bondYield.toFixed(2)}%，股权风险溢价达 ${riskPremium.toFixed(2)}%。且当前股息率高于近 1 年历史均值 ${histAvgYield.toFixed(2)}%，可考虑分批配置红利基金。`;
      } else if (riskPremium >= 2.0 && currentYield >= histAvgYield * 0.9) {
        signal = 'hold';
        signalText = '持续观望';
        signalDesc = '股息率对比合理区间，可持有或小额定投';
        verdictText = `当前股息率 ${currentYield.toFixed(2)}%，较国债收益率溢价 ${riskPremium.toFixed(2)}%，处于合理水平。与历史均值 ${histAvgYield.toFixed(2)}% 相比接近，建议持有或小额定投。`;
      } else {
        signal = 'caution';
        signalText = '暂不宜投';
        signalDesc = '股息率风险溢价不足，等待更好的入场时机';
        verdictText = `当前股息率 ${currentYield.toFixed(2)}% 与国债收益率 ${bondYield.toFixed(2)}% 的利差仅 ${riskPremium.toFixed(2)}%，低于历史水平。当前估值下红利资产性价比不高，建议等待股息率回升后再关注。`;
      }

      this.setData({
        signal,
        signalText,
        signalDesc,
        currentYield: currentYield.toFixed(2),
        bondYield: bondYield.toFixed(2),
        riskPremium: riskPremium.toFixed(2),
        histAvgYield: histAvgYield.toFixed(2),
        verdictText,
        updateTime: data.update_time || ''
      });
    } catch (err) {
      this.setData({
        signal: 'hold',
        signalText: '数据获取失败',
        signalDesc: err.message || '请检查网络连接'
      });
    }
  }
});
