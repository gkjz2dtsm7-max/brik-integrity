window.BRIK_PLACES = (window.BRIK_ROWS||[]).map(function(r){
  return {
    id:r[0], code:r[1], name:r[2], kind:r[3],
    usaSpendingLabel:r[4], perCapitaLabel:r[5],
    overlay:{name:r[6], url:r[7]},
    recordsKit:{name:r[2]+' public records kit', statute:'See official overlay', clock:'Calendar the statutory window'},
    clock:'OPEN. Award-level outcome clock starts when a restricted-use award is attached to this place.',
    fy:'FY2025 (2024-10-01 to 2025-09-30)',
    source:'USAspending API spending_by_geography, place_of_performance, pulled 2026-09-05',
    usaSpendingUrl:'https://www.usaspending.gov/state/'+(r[1]||'')+'/latest',
    parkingWatch:'Scan AG contingent funds, disaster accounts, and unnamed settlement pots before treating cash as program delivery.',
    disburserGraph:'Person-level disburser and certifier names attach at the award row, not at the state total.',
    secondHop:'Vendor and counsel payments are second-hop objects. State totals do not name them.',
    electionsRail:{separate:true, note:'FEC / state campaign filings live on a separate rail. Never added into the grant total above.'},
    topRecipients:[]
  };
});
window.BRIK = {
  product: {
    integrity:'BRIK INTEGRITY', proof:'BRIK PROOF', owner:'BRIK Creative, LLC',
    rule:'Campaign money is never summed into grant totals.',
    heart:'Follow the dollar after award. Name the individual disbursers. Hold them to the stated use. Run a multi-year outcome clock.',
    launched:'2026-09-05', dataPulledAt:'2026-09-05T19:10:00Z', period:'FY2025 place_of_performance'
  },
  metrics: {
    places:(window.BRIK_PLACES||[]).length,
    states:(window.BRIK_PLACES||[]).filter(function(p){return p.kind==='state';}).length,
    foundingCases:5, packets:5, levers:7
  },
  places: window.BRIK_PLACES,
  cases: [
    { id:'winona-cdfi', title:'Bank of Winona CDFI / Treasury awards vs community benefit', place:'ms-winona', placeCode:'MS', status:'OPEN CLOCK', awardClass:'grant', amountLabel:'CDFI / Treasury award cluster', promise:'Community development finance should improve local credit access and community condition.', restrictedUse:'Read award text and TLR rows against second-hop vendors and outcomes.', contingent:'Watch off-ledger community fund labels.', disbursers:['Treasury / CDFI officers of record','Bank of Winona certifying officers'], secondHop:['Counsel and vendor payments after award'], outcomes:'Did Winona-area community condition improve on the stated use?', levers:['grantor clawback','IG','auditor','FCA','public records'], sources:['CDFI TLR','USAspending','Treasury award pages'] },
    { id:'roblox-ms', title:'Roblox-Mississippi digital-literacy pot plus compliance damages', place:'ms', placeCode:'MS', status:'OPEN CLOCK', awardClass:'settlement', amountLabel:'$9M literacy pot + $5M compliance damages', promise:'Funds labeled for digital literacy and compliance remedies.', restrictedUse:'Not general AG operating cash.', contingent:'Watch MS AG Contingent Fund parking.', disbursers:['MS AG disbursers of record'], secondHop:['Literacy vendors','outside counsel fees'], outcomes:'Did residents receive the literacy use, on what timeline?', levers:['contempt','auditor','ethics','public records'], sources:['settlement','MS AG','docket'] },
    { id:'gulf-wastewater', title:'Port St. Joe / Gulf County FL wastewater grant vs water outcomes', place:'fl-gulf', placeCode:'FL', status:'OPEN CLOCK', awardClass:'grant', amountLabel:'$25M wastewater grant (method case)', promise:'Wastewater infrastructure that stops filthy discharge.', restrictedUse:'Wastewater construction, not general city cash.', contingent:'Keep drinking-water failures on a separate clock.', disbursers:['Grantor officers','Port St. Joe / Gulf County certifiers'], secondHop:['Engineers','primes','counsel'], outcomes:'Is the water still filthy after award years?', levers:['clawback','IG','auditor','Ch. 119'], sources:['USAspending','FACTS','minutes'] },
    { id:'meta-ms-contingent', title:'Meta multi-state settlement and MS AG Contingent Fund', place:'ms', placeCode:'MS', status:'OPEN CLOCK', awardClass:'settlement', amountLabel:'MS $189M Contingent Fund purposes TBD', promise:'Settlement purposes as pled.', restrictedUse:'Purpose text controls. Contingent Fund is a parking-account object.', contingent:'MS AG Contingent Fund is a known parking account.', disbursers:['MS AG','Contingent Fund certifiers'], secondHop:['Outside counsel','vendors from contingent draws'], outcomes:'Purpose TBD is not an outcome.', levers:['auditor','ethics','public records'], sources:['settlement','Contingent Fund reports'] },
    { id:'nvlsp-fees', title:'$25M legal-fee siphon pattern (NVLSP PACER class)', place:'us', placeCode:'US', status:'WATCH', awardClass:'judgment', amountLabel:'$25M fees approved', promise:'Class relief is the stated use. Fees are second-hop.', restrictedUse:'Fee award is never rolled into grant totals.', contingent:'Watch distribution timing vs fee collection.', disbursers:['Fee recipients','class counsel of record'], secondHop:['Fee-first detection'], outcomes:'Have class members been paid?', levers:['court','FCA','PACER'], sources:['PACER','fee order'] }
  ],
  levers: [
    {id:'clawback',name:'Grantor clawback',when:'Restricted-use miss or false certification'},
    {id:'ig',name:'Inspector General',when:'Federal award agency IG path'},
    {id:'auditor',name:'Auditor',when:'State or local audit jurisdiction'},
    {id:'fca',name:'False Claims Act vs private certifiers',when:'Knowingly false claims on public money'},
    {id:'contempt',name:'Consent-decree contempt',when:'Court-supervised settlement'},
    {id:'ethics',name:'Ethics / Ch. 839 analog',when:'Official self-dealing facts'},
    {id:'records',name:'Public records',when:'Always the first kit'}
  ],
  kits: [
    {id:'foia',name:'Federal FOIA kit',statute:'5 U.S.C. 552',steps:['Name the agency','Describe records with dates','Ask for fee waiver','Calendar the 20 working-day clock']},
    {id:'fl119',name:'Florida Chapter 119 kit',statute:'Fla. Stat. ch. 119',steps:['Name the custodian','Describe records','Ask for electronic production','Track delay games']},
    {id:'mspr',name:'Mississippi Public Records kit',statute:'Miss. Code Ann. 25-61',steps:['Name the public body','Describe records','Watch seven working days','Escalate constructive denial']}
  ]
};
