(function(){
  const RP=window.ReceiptParser;
  const container=document.getElementById('receiptReviews');
  const status=document.getElementById('receiptStatus');
  const fileInput=document.getElementById('receiptFiles');
  const extractButton=document.getElementById('extractReceipts');
  let isExtracting=false;
  function element(tag,txt,className){
    const node=document.createElement(tag);
    if(txt!==undefined)node.textContent=txt;
    if(className)node.className=className;
    return node;
  }
  function labelField(title,node){
    const label=element('label',undefined,'receipt-field');
    label.append(element('span',title),node);
    return label;
  }
  function numeric(value,placeholder,step){
    const node=element('input');
    node.type='number';
    node.step=step||'0.01';
    node.placeholder=placeholder;
    node.value=value==null?'':String(value);
    return node;
  }
  function textField(value,placeholder){
    const node=element('input');node.type='text';node.value=value||'';node.placeholder=placeholder||'';return node;
  }
  function selectField(choices,initial){
    const node=element('select');
    for(const [v,display] of choices){
      const option=element('option',display);option.value=v;node.append(option);
    }
    node.value=initial||'';
    return node;
  }
  function showError(msg){status.textContent=msg;status.setAttribute('role','status');}
  function makeReview(file,parsed){
    const box=element('section',undefined,'receipt-review');
    const title=element('strong',file.name);
    const img=element('img');img.className='receipt-thumb';img.alt='Selected DraftKings ticket preview';
    const localUrl=URL.createObjectURL(file);img.src=localUrl;img.onload=()=>URL.revokeObjectURL(localUrl);
    box.append(title,img);
    if(parsed.warnings.length){
      const note=element('p',parsed.warnings.join(' '),'receipt-warning');box.append(note);
    }
    const fields=element('div',undefined,'fields');
    const gameChoices=[['','Choose the matchup (required)']];
    const available=[...(args.games||[])].sort((a,b)=>Math.abs(a.week-args.week)-Math.abs(b.week-args.week));
    for(const g of available)gameChoices.push([g.id,g.season+' / Week '+g.week+' · '+g.away+' at '+g.home]);
    const matched=RP.bestGame(parsed.text,available);
    const gameSelect=selectField(gameChoices,matched?.id||'');
    const marketSelect=selectField([['moneyline','Moneyline'],['spread','Spread'],['total','Game total']],parsed.market);
    const pickSelect=selectField([['','Choose the team']], '');
    const sideSelect=selectField([['','Choose Over / Under'],['Over','Over'],['Under','Under']],parsed.side);
    const lineInput=numeric(parsed.line,'Exact spread/total line','0.5');
    const oddsInput=numeric(parsed.odds,'e.g. -110','1');
    const stakeInput=numeric(parsed.stake,'Amount risked','0.01');
    const payoutInput=numeric(parsed.receiptReturn,'Total payout including stake','0.01');
    const ticketInput=textField(parsed.receiptId,'If present');
    const placedInput=textField(parsed.placedAt,'Optional ticket placement time');
    const pickWrapper=labelField('Team picked',pickSelect);
    const sideWrapper=labelField('Total selection',sideSelect);
    const lineWrapper=labelField('Betting line (+3.5, 45.5, etc.)',lineInput);
    fields.append(
      labelField('Game (verify carefully)',gameSelect),
      labelField('Wager type',marketSelect),
      pickWrapper,sideWrapper,lineWrapper,
      labelField('American odds',oddsInput),
      labelField('Amount wagered ($)',stakeInput),
      labelField('Total payout ($, optional)',payoutInput),
      labelField('DraftKings ticket ID (optional)',ticketInput),
      labelField('Placed at (optional)',placedInput)
    );
    function chosenGame(){return available.find(g=>g.id===gameSelect.value);}
    function updateTeams(){
      const old=pickSelect.value;
      pickSelect.replaceChildren();
      const empty=element('option','Choose the bet selection');empty.value='';pickSelect.append(empty);
      const g=chosenGame();
      if(g)for(const team of [g.away,g.home]){const option=element('option',team);option.value=team;pickSelect.append(option);}
      if(g&&[g.home,g.away].includes(old))pickSelect.value=old;
      else pickSelect.value='';
    }
    function updateMarket(){
      const total=marketSelect.value==='total';
      pickWrapper.hidden=total;sideWrapper.hidden=!total;lineWrapper.hidden=marketSelect.value==='moneyline';
    }
    gameSelect.onchange=updateTeams;
    marketSelect.onchange=updateMarket;
    updateTeams();updateMarket();
    box.append(fields);
    const warnings=element('p','Verify the matchup, selection, line, actual odds, stake, and payout against your screenshot. OCR may misread signs and numbers. No bet is saved until you confirm.','muted');
    box.append(warnings);
    const confirmation=element('input');confirmation.type='checkbox';
    const confirmLabel=labelField('I verified this ticket against the screenshot',confirmation);
    confirmLabel.className='receipt-checkbox';box.append(confirmLabel);
    const acceptSimilar=element('input');acceptSimilar.type='checkbox';
    const similarLabel=labelField('Allow a similar existing wager (only if this is a separate bet)',acceptSimilar);
    similarLabel.className='receipt-checkbox';box.append(similarLabel);
    const actions=element('div',undefined,'actions');
    const save=element('button','Save verified bet','primary');save.type='button';
    const feedback=element('p',undefined,'receipt-warning');feedback.setAttribute('role','status');
    if(parsed.unsupported){save.disabled=true;feedback.textContent='Parlays, SGPs, and other multi-leg tickets are not supported by this importer.';}
    save.onclick=()=>{
      feedback.textContent='';
      if(!storageOK){feedback.textContent='Your browser storage is unavailable. Restore access before saving.';return;}
      if(!confirmation.checked){feedback.textContent='Check the verification box after comparing the fields to your ticket.';return;}
      try{
        const game=chosenGame();
        if(!game)throw Error('Select the correct game. Change the season/week above if it is not listed.');
        const receiptId=ticketInput.value.trim();
        const bet=C.grade(C.validate({
          type:'single',source:'screenshot',id:crypto.randomUUID(),
          created:new Date().toISOString(),gameId:game.id,home:game.home,away:game.away,
          season:game.season,week:game.week,team:marketSelect.value==='total'?'':pickSelect.value,
          market:marketSelect.value,side:sideSelect.value,line:lineInput.value,
          stake:Number(stakeInput.value),odds:Number(oddsInput.value),
          receiptReturn:payoutInput.value===''?null:Number(payoutInput.value),
          receiptId,placedAt:placedInput.value,book:'DraftKings',
          override:'Auto',autoResult:'Pending'
        }),args.games);
        if(receiptId&&bets.some(b=>b.book==='DraftKings'&&b.receiptId&&b.receiptId.toLowerCase()===receiptId.toLowerCase())){
          throw Error('That DraftKings ticket ID has already been imported.');
        }
        const similar=bets.some(b=>b.type!=='parlay'&&b.gameId===bet.gameId&&b.market===bet.market&&
          b.team===bet.team&&b.side===bet.side&&b.line===bet.line&&b.odds===bet.odds&&
          b.stake===bet.stake&&b.book==='DraftKings');
        if(similar&&!acceptSimilar.checked)throw Error('A similar wager is already saved. Confirm it is a separate bet and check “Allow a similar existing wager” to proceed.');
        if(bets.length>=5000)throw Error('Tracker limit is 5,000 bets.');
        if(persist([...bets,bet])){
          save.disabled=true;confirmation.disabled=true;
          feedback.textContent='Saved successfully. Screenshot was not stored.';
          feedback.className='receipt-success';
          message('DraftKings bet imported into My Bets.');
          render();
        }else{feedback.textContent='Could not save the bet to browser storage.';}
      }catch(e){feedback.textContent=e.message;}
    };
    actions.append(save);box.append(actions,feedback);
    const raw=element('details');raw.append(element('summary','View recognized text (to help correct OCR)'));
    const rawText=element('pre',parsed.text,'receipt-raw');raw.append(rawText);box.append(raw);
    return box;
  }
  extractButton.onclick=async()=>{
    if(isExtracting)return;
    const files=[...fileInput.files];
    if(!files.length){showError('Choose at least one screenshot first.');return;}
    if(files.length>5){showError('Import up to five screenshots at a time.');return;}
    if(files.some(f=>!f.type.startsWith('image/')||f.size>8*1024*1024)){showError('Only images up to 8 MB each are supported.');return;}
    if(!window.Tesseract){showError('Free OCR library could not load. Check your internet connection and reload the app.');return;}
    isExtracting=true;extractButton.disabled=true;container.replaceChildren();
    let worker;
    try{
      showError('Initializing on-device OCR. The first use downloads language data.');
      worker=await window.Tesseract.createWorker('eng',1,{
        logger:m=>{if(m.status)showError('Reading screenshot: '+m.status+(m.progress?' '+Math.round(m.progress*100)+'%':''));}
      });
      for(let i=0;i<files.length;i++){
        showError('Reading receipt '+(i+1)+' of '+files.length+'...');
        try{
          const result=await worker.recognize(files[i]);
          const parsed=RP.parse(result.data.text);
          container.append(makeReview(files[i],parsed));
        }catch(e){
          container.append(element('p',files[i].name+': OCR failed: '+e.message,'receipt-warning'));
        }
      }
      showError('Review every ticket carefully, then save each separately.');
    }catch(e){showError('Screenshot recognition failed: '+e.message+'. Check network access to the free OCR files.');}
    finally{if(worker)await worker.terminate().catch(()=>{});isExtracting=false;extractButton.disabled=false;height();}
  };
})();
