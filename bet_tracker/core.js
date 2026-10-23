(function(root){
  const round = x => Math.round((x + Number.EPSILON) * 100) / 100;
  function parlayResult(legs) {
    if(legs.some(l=>l.autoResult==='Lost')) return 'Lost';
    if(legs.every(l=>l.autoResult==='Won')) return 'Won';
    if(legs.some(l=>l.autoResult==='Pending')) return 'Pending';
    return 'Needs review';
  }
  function validateParlay(b) {
    if(!Array.isArray(b.legs)||b.legs.length<2||b.legs.length>20) throw Error('A parlay needs 2–20 moneyline legs.');
    const legs=b.legs.map(l=>{
      if(!l||l.market!=='moneyline') throw Error('Only moneyline parlay legs are supported.');
      const clean=validate({...l,type:'single',id:b.id,created:b.created,stake:1,receiptReturn:null,override:'Auto',book:''});
      if(clean.season!==b.season||clean.week!==b.week) throw Error('Parlay legs must share the recorded season and week.');
      return {gameId:clean.gameId,home:clean.home,away:clean.away,team:clean.team,season:clean.season,week:clean.week,odds:clean.odds,autoResult:clean.autoResult,market:'moneyline'};
    });
    if(new Set(legs.map(l=>l.gameId)).size!==legs.length) throw Error('Each parlay leg must be a different game.');
    const first=legs[0];
    const clean=validate({...b,type:'single',gameId:first.gameId,home:first.home,away:first.away,team:first.team,autoResult:'Pending'});
    const {id,created,season,week,stake,odds,book,override,receiptReturn}=clean;
    return {type:'parlay',id,created,season,week,stake,odds,book,override,receiptReturn,legs,autoResult:parlayResult(legs)};
  }
  function validate(b) {
    if(b?.type==='parlay') return validateParlay(b);
    if(b?.type && b.type!=='single') throw Error('Unsupported bet type.');
    if (!b || typeof b !== 'object' || typeof b.id !== 'string' || !b.id || b.id.length>100) throw Error('Invalid bet ID.');
    for (const k of ['gameId','home','away','created']) if(typeof b[k]!=='string'||!b[k]||b[k].length>200) throw Error('Invalid bet details.');
    if(b.home===b.away) throw Error('Invalid matchup.');
    const market=b.market||'moneyline';
    if(!['moneyline','spread','total'].includes(market)) throw Error('Unsupported wager market.');
    const team=market==='total'?'':b.team;
    if(market!=='total'&&![b.home,b.away].includes(team)) throw Error('Pick must be one of the teams.');
    const side=market==='total'?b.side||'':null;
    if(market==='total'&&!['Over','Under'].includes(side)) throw Error('Total needs an Over or Under selection.');
    const line=market==='moneyline'?null:Number(b.line);
    if(market!=='moneyline'&&(!Number.isFinite(line)||Math.abs(line)>200||b.line===''||b.line==null)) throw Error('Enter the spread or total points line.');
    if(market==='total'&&line<0) throw Error('Total points line cannot be negative.');
    if(!Number.isInteger(b.season)||b.season<2001||b.season>2100||!Number.isInteger(b.week)||b.week<1||b.week>30) throw Error('Invalid season or week.');
    if(!Number.isFinite(b.stake)||b.stake<0.01||b.stake>100000||!Number.isInteger(b.odds)||Math.abs(b.odds)<100||Math.abs(b.odds)>1000000) throw Error('Enter a positive stake and valid American odds (such as -150 or +120).');
    if(!['Auto','Won','Lost','Push','Void'].includes(b.override)) throw Error('Invalid result override.');
    if(!['Pending','Won','Lost','Push'].includes(b.autoResult)) throw Error('Invalid automatic result.');
    const receiptReturn=b.receiptReturn==null?null:b.receiptReturn;
    if(receiptReturn!==null&&(!Number.isFinite(receiptReturn)||receiptReturn<b.stake||receiptReturn>1000000000)) throw Error('Receipt payout must include the stake and be at least the stake.');
    const source=b.source==='screenshot'?'screenshot':'manual';
    const receiptId=String(b.receiptId||'').trim().slice(0,100);
    const placedAt=String(b.placedAt||'').trim().slice(0,80);
    return {type:'single',market,line,side,source,receiptId,placedAt,receiptReturn:receiptReturn===null?null:round(receiptReturn),id:b.id,gameId:b.gameId,home:b.home,away:b.away,team,created:b.created,season:b.season,week:b.week,stake:round(b.stake),odds:b.odds,book:String(b.book||'').slice(0,100),override:b.override,autoResult:b.autoResult};
  }
  function grade(b,games) {
    if(b.type==='parlay') {
      const legs=b.legs.map(l=>grade(l,games));
      return {...b,legs,autoResult:parlayResult(legs)};
    }
    const g=games.find(g=>g.id===b.gameId&&g.season===b.season&&g.home===b.home&&g.away===b.away);
    if(!g) return {...b};
    let autoResult='Pending';
    if(g.completed&&Number.isFinite(g.homeScore)&&Number.isFinite(g.awayScore)) {
      if(b.market==='spread'){
        const margin=(b.team===g.home?g.homeScore-g.awayScore:g.awayScore-g.homeScore)+b.line;
        autoResult=Math.abs(margin)<1e-8?'Push':margin>0?'Won':'Lost';
      } else if(b.market==='total'){
        const delta=g.homeScore+g.awayScore-b.line;
        autoResult=Math.abs(delta)<1e-8?'Push':((delta>0)===(b.side==='Over')?'Won':'Lost');
      } else {
        autoResult=g.homeScore===g.awayScore?'Push':((g.homeScore>g.awayScore?g.home:g.away)===b.team?'Won':'Lost');
      }
    }
    return {...b,autoResult};
  }
  function outcome(b) {
    const status=b.override==='Auto'?b.autoResult:b.override;
    const winProfit=b.receiptReturn==null?round(b.stake*(b.odds>0?b.odds/100:100/Math.abs(b.odds))):round(b.receiptReturn-b.stake);
    const returned=status==='Won'?round(b.stake+winProfit):status==='Lost'?0:['Push','Void'].includes(status)?b.stake:null;
    return {status,winProfit,winReturn:round(b.stake+winProfit),returned,profit:returned===null?null:round(returned-b.stake)};
  }
  function stats(bets) {
    const rows=bets.map(b=>({...b,...outcome(b)}));
    const total=key=>round(rows.filter(key).reduce((s,b)=>s+b.stake,0));
    const won=rows.filter(b=>b.status==='Won').length,lost=rows.filter(b=>b.status==='Lost').length;
    const settledStake=total(b=>['Won','Lost','Push'].includes(b.status));
    const profit=round(rows.reduce((s,b)=>s+(b.profit||0),0));
    return {bets:rows.length,won,lost,push:rows.filter(b=>b.status==='Push').length,void:rows.filter(b=>b.status==='Void').length,pending:total(b=>['Pending','Needs review'].includes(b.status)),settledStake,profit,returned:round(rows.reduce((s,b)=>s+(b.returned||0),0)),roi:settledStake?profit/settledStake:null,winRate:won+lost?won/(won+lost):null};
  }
  function clearHistory(confirmation) {
    if(confirmation!=='CLEAR') throw Error('Type CLEAR to confirm deleting all betting history.');
    return [];
  }
  root.TrackerCore={validate,grade,outcome,stats,clearHistory};
  if(typeof module!=='undefined') module.exports=root.TrackerCore;
})(typeof window==='undefined'?globalThis:window);

