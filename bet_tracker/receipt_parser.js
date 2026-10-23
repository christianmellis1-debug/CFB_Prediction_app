(function(root){
  // Best-effort DraftKings receipt parsing. Never save unreviewed OCR results.
  function amount(text, pattern){
    const m=text.match(pattern);
    return m ? Number(m[1].replace(/,/g,'')) : null;
  }
  function parse(text){
    text=String(text||'').replace(/\u00a0/g,' ').replace(/[−–—]/g,'-');
    const compact=text.replace(/[ \t]+/g,' ');
    const lower=compact.toLowerCase();
    const unsupported=/\b(parlay|same.game.parlay|round.robin|teaser|sgp)\b/i.test(compact);
    const totalMatch=compact.match(/\b(over|under)\s*(?:total\s*)?(\d{2,3}(?:\.\d+)?)\b/i)
       ||compact.match(/\b([ou])\s*(\d{2,3}(?:\.\d+)?)\b/i);
    const market=totalMatch||/\b(total points|game total|over\/under)\b/i.test(compact)?'total':
      /\b(point spread|spread|alternate spread)\b/i.test(compact)?'spread':'moneyline';
    const side=totalMatch?(totalMatch[1].toLowerCase().startsWith('o')?'Over':'Under'):'';
    let line=market==='total'&&totalMatch?Number(totalMatch[2]):null;
    if(market==='spread'){
      const m=compact.match(/\b(?:spread|handicap)\s*[:\-]?\s*[^\n]{0,65}?\b([+-]\d{1,2}(?:\.\d+)?)\b/i)||
        compact.match(/(?:^|[\s(])([+-]\d{1,2}(?:\.\d+)?)(?!\d)/m);
      line=m?Number(m[1]):null;
    }
    const oddsCandidates=[...compact.matchAll(/(^|[\s(])([+-]\s?\d{3,5})(?=$|[\s),])/gm)].map(m=>Number(m[2].replace(/\s/g,''))).filter(x=>Math.abs(x)>=100);
    const labeledOdds=compact.match(/\b(?:american odds|odds|price)\s*[:\-]?\s*([+-]\s?\d{3,5})\b/i);
    const odds=labeledOdds?Number(labeledOdds[1].replace(/\s/g,'')):(oddsCandidates.length===1?oddsCandidates[0]:null);
    const stake=amount(compact,/\b(?:wager(?:ed)?|stake|risk(?:ed)?|bet amount|amount bet)\s*[:\-]?\s*\$?\s*([\d,]+(?:\.\d{1,2})?)/i);
    let receiptReturn=amount(compact,/\b(?:potential payout|total payout|possible payout|estimated payout|payout|to pay|total return|returns?)\s*[:\-]?\s*\$?\s*([\d,]+(?:\.\d{1,2})?)/i);
    const toWin=amount(compact,/\b(?:to win|potential winnings?|profit)\s*[:\-]?\s*\$?\s*([\d,]+(?:\.\d{1,2})?)/i);
    if(receiptReturn===null&&toWin!==null&&stake!==null)receiptReturn=Math.round((stake+toWin)*100)/100;
    const ticket=compact.match(/\b(?:ticket|receipt|wager|bet)\s*(?:number|no\.?|id|#)\s*[:#\-]?\s*([a-z0-9-]{6,60})\b/i);
    const date=compact.match(/\b(?:placed|accepted)\s*(?:on|at)?\s*[:\-]?\s*([A-Za-z0-9 ,/:.-]{6,45})/i);
    const warnings=[];
    if(unsupported)warnings.push('Parlay or multi-leg ticket detected. This version imports straight bets only.');
    if(stake===null)warnings.push('Stake was not recognized. Enter it from the receipt.');
    if(odds===null)warnings.push('American odds were not identified confidently. Enter the receipt odds.');
    if(market!=='moneyline'&&line===null)warnings.push('Spread/total line was not recognized. Enter the exact line.');
    if(market==='total'&&!side)warnings.push('Choose Over or Under.');
    if(oddsCandidates.length>1&&!labeledOdds)warnings.push('Multiple odds were found. Verify which belongs to this wager.');
    if(receiptReturn!==null&&stake!==null&&receiptReturn<stake){
      warnings.push('Detected payout is below the stake. Check the receipt.');
      receiptReturn=null;
    }
    return {market,side,line,odds,stake,receiptReturn,receiptId:ticket?ticket[1]:'',placedAt:date?date[1].trim():'',unsupported,warnings,text:compact};
  }
  function bestGame(text,games){
    const normalized=s=>String(s||'').toLowerCase().replace(/[^a-z0-9 ]/g,' ').replace(/\s+/g,' ').trim();
    const hay=' '+normalized(text)+' ';
    let winner=null,best=0,tie=false;
    for(const g of games){
      const home=normalized(g.home),away=normalized(g.away);
      const hasHome=home.length>=4&&hay.includes(' '+home+' ');
      const hasAway=away.length>=4&&hay.includes(' '+away+' ');
      const score=(hasHome?1:0)+(hasAway?1:0);
      if(score>best){winner=g;best=score;tie=false;}
      else if(score===best&&score>0)tie=true;
    }
    return !tie&&best===2?winner:null;
  }
  root.ReceiptParser={parse,bestGame};
  if(typeof module!=='undefined')module.exports=root.ReceiptParser;
})(typeof window==='undefined'?globalThis:window);
