window.BRIK = {
  product: {
    integrity: 'BRIK INTEGRITY',
    proof: 'BRIK PROOF',
    owner: 'BRIK Creative, LLC',
    rule: 'Campaign money is never summed into grant totals.',
    heart: 'Follow the dollar after award. Name the individual disbursers. Hold them to the stated use. Run a multi-year outcome clock.',
    launched: '2026-09-05'
  },
  metrics: { places: 5, foundingCases: 5, awardsTracked: 18, packets: 5, levers: 7 },
  places: [
    { id: 'us', name: 'United States', kind: 'nation', summary: 'National ledger. Grants and settlements only in grant totals. Elections sit on a separate rail.' },
    { id: 'fl', name: 'Florida', kind: 'state', summary: 'Pilot state. FACTS plus USAspending plus Chapter 119 kits.' },
    { id: 'fl-gulf', name: 'Gulf County, Florida', kind: 'county', summary: 'Port St. Joe wastewater and drinking-water outcome clock.' },
    { id: 'ms', name: 'Mississippi', kind: 'state', summary: 'CDFI awards, AG Contingent Fund parking, Roblox digital-literacy pot.' },
    { id: 'ms-winona', name: 'Winona / Montgomery County, MS', kind: 'city', summary: 'Bank of Winona CDFI / Treasury awards vs community condition.' }
  ],
  cases: [
    { id: 'winona-cdfi', title: 'Bank of Winona CDFI / Treasury awards vs community benefit', place: 'ms-winona', status: 'OPEN CLOCK', awardClass: 'grant', amountLabel: 'CDFI / Treasury award cluster (see packet)', promise: 'Community development finance is supposed to improve local credit access and measurable community condition.', restrictedUse: 'Award text and TLR rows must be read against actual second-hop vendors and local outcomes, not press releases.', contingent: 'None alleged as a parking account. Watch any off-ledger community fund labels.', disbursers: ['Treasury / CDFI Fund program officers of record', 'Bank of Winona certifying officers'], secondHop: ['Counsel and vendor payments after award go on the second-hop graph'], outcomes: 'Multi-year clock: did Winona-area community condition improve on the stated use?', levers: ['grantor clawback', 'IG', 'auditor', 'FCA against private certifiers', 'public records'], sources: ['CDFI Transaction Level Reports', 'USAspending', 'Treasury award pages'] },
    { id: 'roblox-ms', title: 'Roblox-Mississippi digital-literacy pot plus compliance damages', place: 'ms', status: 'OPEN CLOCK', awardClass: 'settlement', amountLabel: '$9M digital-literacy pot + $5M compliance damages (method case)', promise: 'Funds labeled for digital literacy and compliance remedies for Mississippi residents.', restrictedUse: 'Literacy pot is not general AG operating cash. Compliance damages are not a slush label.', contingent: 'Watch whether any slice is parked in the MS AG Contingent Fund.', disbursers: ['Mississippi Attorney General office disbursers of record', 'settlement administrator if named'], secondHop: ['Vendors hired to deliver digital literacy programs', 'outside counsel fee rows'], outcomes: 'Did Mississippi students or residents receive the literacy use, on what timeline?', levers: ['consent-decree contempt', 'auditor', 'ethics', 'public records'], sources: ['settlement documents', 'MS AG releases', 'court docket'] },
    { id: 'gulf-wastewater', title: 'Port St. Joe / Gulf County FL $25M wastewater grant vs water outcomes', place: 'fl-gulf', status: 'OPEN CLOCK', awardClass: 'grant', amountLabel: '$25M wastewater grant (method case)', promise: 'Wastewater infrastructure sufficient to stop filthy discharge and protect drinking-water adjacent systems.', restrictedUse: 'Wastewater construction and related restricted uses. Not general city operating cash.', contingent: 'Separate drinking-water failures stay on their own clock. Do not blend.', disbursers: ['Federal / state grantor officers', 'City of Port St. Joe / Gulf County certifiers'], secondHop: ['Engineering firms', 'construction primes', 'counsel'], outcomes: 'Is the water still filthy after award years? Outcome clock is the product heart.', levers: ['grantor clawback', 'IG', 'auditor', 'public records', 'Florida Ch. 119'], sources: ['USAspending', 'Florida FACTS', 'city / county minutes', 'resident evidence packets'] },
    { id: 'meta-ms-contingent', title: 'Meta / Facebook multi-state settlement and MS AG Contingent Fund', place: 'ms', status: 'OPEN CLOCK', awardClass: 'settlement', amountLabel: 'MS $189M into AG Contingent Fund purposes TBD (method case)', promise: 'Multi-state consumer settlement purposes as pled in the agreement.', restrictedUse: 'Settlement purpose text controls. Contingent Fund is a first-class parking-account object.', contingent: 'MS AG Contingent Fund is a known parking account for settlement cash.', disbursers: ['Mississippi Attorney General', 'Contingent Fund certifiers'], secondHop: ['Outside counsel', 'vendors paid from contingent draws'], outcomes: 'Purpose TBD is not an outcome. Clock starts when purpose is named and cash moves.', levers: ['auditor', 'ethics', 'public records', 'legislature oversight'], sources: ['multi-state settlement', 'MS AG Contingent Fund reports', 'budget documents'] },
    { id: 'nvlsp-fees', title: '$25M legal-fee siphon pattern (NVLSP PACER class)', place: 'us', status: 'WATCH', awardClass: 'judgment', amountLabel: '$25M fees approved, distributions not yet the story', promise: 'Class relief is the stated use. Fees are a second-hop, not the grant total.', restrictedUse: 'Fee award is not community benefit and is never rolled into grant totals.', contingent: 'Watch distribution timing vs fee collection timing.', disbursers: ['Court-approved fee recipients', 'class counsel of record'], secondHop: ['Fee-first detection is the point of this teacher case'], outcomes: 'Have class members been paid? Clock on distributions, not on fee approval headlines.', levers: ['court', 'FCA against private certifiers where facts support', 'public records / PACER'], sources: ['PACER docket', 'fee order', 'distribution reports'] }
  ],
  levers: [
    { id: 'clawback', name: 'Grantor clawback', when: 'Restricted-use miss or false certification' },
    { id: 'ig', name: 'Inspector General', when: 'Federal award agency IG path' },
    { id: 'auditor', name: 'Auditor', when: 'State or local audit jurisdiction' },
    { id: 'fca', name: 'False Claims Act vs private certifiers', when: 'Knowingly false claims on public money' },
    { id: 'contempt', name: 'Consent-decree contempt', when: 'Court-supervised settlement' },
    { id: 'ethics', name: 'Ethics / Ch. 839 analog', when: 'Official self-dealing facts' },
    { id: 'records', name: 'Public records', when: 'Always available as the first kit' }
  ],
  kits: [
    { id: 'foia', name: 'Federal FOIA kit', statute: '5 U.S.C. 552', steps: ['Name the agency', 'Describe records with dates', 'Ask for fee waiver as public interest', 'Calendar the 20 working-day clock'] },
    { id: 'fl119', name: 'Florida Chapter 119 kit', statute: 'Fla. Stat. ch. 119', steps: ['Name the custodian', 'Describe records', 'Ask for electronic production', 'Track delay and estimate games'] },
    { id: 'mspr', name: 'Mississippi Public Records kit', statute: 'Miss. Code Ann. 25-61', steps: ['Name the public body', 'Describe records', 'Watch the seven-day working response', 'Escalate on constructive denial'] }
  ]
};
