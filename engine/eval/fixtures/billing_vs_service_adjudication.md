# billing_charge ↔ service_fault — adjudication list (23 rows, 57% of all category errors)
These are the rows where gold and model disagree on exactly the billing↔service boundary you flagged wobbling on. For each, decide the TRUE category. Then we tune the prompt to the corrected boundary — not to the current labels.
## Proposed decision rule (edit it — this is the thing we'll encode)
- **billing_charge** = the CORE grievance is a specific charge/fee/amount/balance being wrong, OR an inaccurate credit-report/account RECORD (a reporting problem). The dispute is about *the number or the record*.
- **service_fault** = the CORE grievance is the company's HANDLING — it mishandled, ignored, delayed, or botched a dispute/claim/request. The money may be incidental; the complaint is about *conduct/process/failure-to-act*.
- **Tiebreak** when both are present: classify by the PRIMARY ask/harm. Charge itself wrong → billing_charge. Charge is settled/secondary and they're angry about being ignored or jerked around → service_fault.

---
| # | id | current gold | model said | your call |
|---|---|---|---|---|
| 1 | 24118620 | billing_charge | service_fault | ______ |
| 2 | 24225751 | billing_charge | service_fault | ______ |
| 3 | 24473525 | billing_charge | service_fault | ______ |
| 4 | 24491609 | billing_charge | service_fault | ______ |
| 5 | 24476203 | service_fault | billing_charge | ______ |
| 6 | 24478374 | service_fault | billing_charge | ______ |
| 7 | 24479671 | service_fault | billing_charge | ______ |
| 8 | 24483813 | service_fault | billing_charge | ______ |
| 9 | 24490268 | service_fault | billing_charge | ______ |
| 10 | 24508215 | service_fault | billing_charge | ______ |
| 11 | 24510840 | service_fault | billing_charge | ______ |
| 12 | 24514281 | service_fault | billing_charge | ______ |
| 13 | 24516265 | service_fault | billing_charge | ______ |
| 14 | 24520638 | service_fault | billing_charge | ______ |
| 15 | 7448709 | service_fault | billing_charge | ______ |
| 16 | 7450437 | service_fault | billing_charge | ______ |
| 17 | 7450469 | service_fault | billing_charge | ______ |
| 18 | 7450669 | service_fault | billing_charge | ______ |
| 19 | 7450993 | service_fault | billing_charge | ______ |
| 20 | 7451012 | service_fault | billing_charge | ______ |
| 21 | 7451352 | service_fault | billing_charge | ______ |
| 22 | 7452822 | service_fault | billing_charge | ______ |
| 23 | 7452911 | service_fault | billing_charge | ______ |

---

## Claude's adversarial read (PROPOSAL ONLY — not gold; your `your call` column above is untouched)
Read all 23. Sorted by the CORE grievance, which is fold-independent. The decisive fact: **~11 rows are
credit-report/record-accuracy disputes** ("this item on my report is factually wrong — fix/remove it"),
which are neither a wrong-charge nor an ordinary service-handling failure. They flip entirely on ONE
decision (below). I did NOT pick that decision or re-score against it — that is self-grading (§10).

**THE ONE DECISION (resolves ~10–15 of the 23):** where do record-accuracy disputes go?
- (A) `billing_charge` — your drafted rule. Flips ~10 gold labels to the model's side (model was right).
- (B) `service_fault` — "failure to keep/correct an accurate record is a handling failure." Gold stands; tune the prompt.
- (C) a NEW governed category `record_dispute` — cleanest; the honest read of why finance starved the taxonomy. **Claude's rec.** Governed-core change → your call, logged.

| # | id | core grievance (my read) | unambiguous? | if fold=A | if fold=B/C→service |
|---|---|---|---|---|---|
| 1 | 24118620 | funds wrongfully removed after refund | **billing (model wrong)** | billing | billing |
| 2 | 24225751 | fraud claim denied twice — process | service (leans, model right) | service | service |
| 3 | 24473525 | deceptive overdraft fees | **billing (model wrong)** | billing | billing |
| 4 | 24491609 | unauth txns + bank won't help refund | service (leans, model right) | service | service |
| 5 | 24476203 | bank REFUSES to evaluate dispute | **service (model wrong)** | service | service |
| 6 | 24478374 | paid off, still reports $24k owed | record-accuracy | billing | service/record |
| 7 | 24479671 | disputed, agency failed to validate | record + validation-fail | billing | service/record |
| 8 | 24483813 | "inaccurate info on report, remove" | record-accuracy | billing | service/record |
| 9 | 24490268 | identical to 8 | record-accuracy | billing | service/record |
| 10 | 24508215 | inaccurate acct added, no validation | record + process | billing | service/record |
| 11 | 24510840 | dispute accuracy, delete if unverified | record-accuracy | billing | service/record |
| 12 | 24514281 | re-aging, wrong Date Opened | record-accuracy | billing | service/record |
| 13 | 24516265 | sent validation notice, no validation | **service (model wrong)** | service | service |
| 14 | 24520638 | no initial notice, no validation sent | **service (model wrong)** | service | service |
| 15 | 7448709 | remove inaccurate late payment | record-accuracy | billing | service/record |
| 16 | 7450437 | reporting me late, never late | record-accuracy | billing | service/record |
| 17 | 7450469 | owed $6200 refund, got $500 | billing (money owed, model right) | billing | billing |
| 18 | 7450669 | trip-delay coverage claim $230 | service (claim handling, leans) | service | service |
| 19 | 7450993 | remove inaccuracies, timely payer | record-accuracy | billing | service/record |
| 20 | 7451012 | fraudulent line, unauth charges | billing (fraud/charges, model right) | billing | billing |
| 21 | 7451352 | wants to PAY, jerked around 10 calls | **service (model wrong)** | service | service |
| 22 | 7452822 | fraud inquiry, CapOne won't respond 6mo | service (leans, model right) | service | service |
| 23 | 7452911 | settled, balance now shows wrong amount | record/number-wrong | billing | service/record |

**Unambiguous model errors (fold-independent): 6 rows — 1, 3, 5, 13, 14, 21.** Everything else hinges on
the fold. Fill `your call` (or just tell me the fold letter and I'll apply it) → then the TRUE baseline.

---

## Narratives

### 1. 24118620 — gold=`billing_charge` · model=`service_fault`
Someone posed as an attorney and he requested {$500.00} from me. He was not an attorney. I filed for a refund that was issued but this creep company Fidelity information services then removed my money and placed it in their account. I have the texts messages from this lowlife scammer.

### 2. 24225751 — gold=`billing_charge` · model=`service_fault`
On XX/XX/XXXX at approximately XXXXXXXX XXXX., two XXXX XXXX XXXX approached me and asked if I would donate to their basketball team. I told them I did not have any cash, and they asked if I could send a donation to their XXXX via XXXX. I agreed, and they took my phone to enter the payment information. Instead of sending a donation to their coach, they used my phone to transfer {$2000.00} to themselves or an unknown recipient. They then dropped my phone and ran away. I immediately contacted Bank of America to report the fraudulent transaction. After two days, my claim was denied. On Monday, XX/XX/XXXX, I reopened the claim and provided the co

### 3. 24473525 — gold=`billing_charge` · model=`service_fault`
I am filing a complaint against Truist Bank regarding predatory and deceptive overdraft fee practices. On XX/XX/year>, I checked my available account balance multiple times using the bank 's official application. The software explicitly displayed a positive balance, indicating the funds were cleared and available. Relying on this accurate ledger, I processed an online transfer of XXXX XXXX.However, Truist intentionally withheld posting older pending items during the business day. Instead, they processed transactions as a midnight batch overnight. This delayed batch processing artificially drove my account deep into a negative balance while I 

### 4. 24491609 — gold=`billing_charge` · model=`service_fault`
Approximately XX/XX/year>, I recognized there were unauthorized transactions that were approved through my bank. I contacted the bank and they have given me such a hard time trying to get my funds back. They have continued accusing me of using the funds. I have gone as far as filing a police report and actually finding the individual that has stolen from me. The police actually has her in custody and continues to contact me about the the charges filed against her on my behalf, however, no one from the bank institution has stepped up to assist me with acknowledging that I had nothing to do with the fraudulent incident and to help me recover my

### 5. 24476203 — gold=`service_fault` · model=`billing_charge`
WSFS Bank is refusing to evaluate a valid dispute for XXXX XXXX under XXXX network rules. On XX/XX/year>, I paid {$770.00} at XXXX XXXX XXXX XXXX # XXXX ) for a throttle body replacement to fix a vehicle stalling issue. The repair was ineffective, and the vehicle stalled again immediately. I returned to the same XXXX XXXX location just XXXX miles later. XXXX XXXX re-diagnosed the vehicle and identified the actual issue as a Crankshaft Position Sensor ( Invoice # XXXX ), proving the initial {$770.00} repair was based on an incorrect diagnosis and failed to correct the problem. Despite submitting both matching invoices showing the XXXX gap to X

### 6. 24478374 — gold=`service_fault` · model=`billing_charge`
My partner and I both owned a debt for a truck. He was primary, I was co signer. The vehicle was a voluntary repo. The lender was Auto Finance USA. The debt was paid off XX/XX/XXXX. He was being garnished. We paid the remaining lump sum amount of {$15000.00} in full. On XX/XX/XXXX, we received our letter of satisfaction by the court. It was the release of judgment and release of any judgment liens. It was signed. The garnishment stopped as ordered. We didn't think much else of it and that was that. We checked both of our credit reports at the end of last month ( XXXX ) and realized the company still showed both my partner and I owed them {$24

### 7. 24479671 — gold=`service_fault` · model=`billing_charge`
On XX/XX/year>, I disputed a collection account reported by Pacific Credit Exchange for XXXX XXXX with XXXX XXXX responded on XX/XX/year>, marking the account as Remains, but they did not provide any documentation such as an itemized statement, proof of liability, or assignment from XXXX XXXX. This is not proper verification under the Fair Credit Reporting Act. I requested validation of the debt, including an itemized statement, proof of liability, documentation of assignment from XXXX XXXX to Pacific Credit Exchange, and any contract or billing breakdown. Pacific Credit Exchange failed to provide any of this information, yet Experian continu

### 8. 24483813 — gold=`service_fault` · model=`billing_charge`
There are collection accounts on my report that I believe contain inaccurate information. Under my rights pursuant to XXXX XXXX XXXX ( b ) and XXXX XXXX XXXX, I am entitled to an accurate credit report. I request a review of these entries, and if they can not be verified as accurate, I ask that they be removed.

### 9. 24490268 — gold=`service_fault` · model=`billing_charge`
There are collection accounts on my report that I believe contain inaccurate information. Under my rights pursuant to 15 USC 1681e ( b ) and 15 USC 1681i, I am entitled to an accurate credit report. I request a review of these entries, and if they can not be verified as accurate, I ask that they be removed.

### 10. 24508215 — gold=`service_fault` · model=`billing_charge`
Im writing to file a complaint against I.C. SYSTEM, INC for violating my consumer rights under 12 CFR 1006.34 and 15 USC 1681-s2 ( 7 ) ( A ). Theyve added an inaccurate account to my consumer report without giving me the required validation info, as outlined in 12 CFR 1006.34 ( b ) ( 5 ). On top of that, I havent been given a chance to dispute the account, which Im entitled to under 12 CFR 1006.34 ( c ) ( 4 ) ( i ). Overall, their actions are not only against federal regulations but also misleading and deceptive

### 11. 24510840 — gold=`service_fault` · model=`billing_charge`
I dispute the accuracy and completeness of this Waypoint Resource Group collection account. Please verify the original creditor information, balance, date of first delinquency, payment history, and your authority to report this account. If the information can not be verified as accurate and complete, I request that it be deleted from my credit file. If the account is verified, I respectfully request that Waypoint Resource Group and the original creditor consider a goodwill or courtesy deletion. I experienced financial hardship that contributed to this account becoming delinquent and have worked diligently to restore my financial stability. I 

### 12. 24514281 — gold=`service_fault` · model=`billing_charge`
I disputed a medical collection with Aargon Agency Inc. ( Account # XXXX ) via XXXX ( Report # XXXX ). XXXX rejected my dispute and verified the account. However, Aargon 's own official 5-page hospital ledger ( attached ) shows the registration date was XX/XX/2024. Aargon is illegally reporting the 'Date Opened ' as one month ago on my credit file. This is a deliberate re-aging violation of the FCRA designed to artificially damage my credit score. Furthermore, Page 2 shows all actual medical procedure balances are {$0.00}. I demand immediate deletion of this unverified, non-compliant trade line.

### 13. 24516265 — gold=`service_fault` · model=`billing_charge`
On XX/XX/year>, I submitted a formal written debt validation and dispute notice via email to L.J. Ross Associates regarding an alleged XXXX debt. Prior to placing this account on my credit report, the collection agency made XXXX attempts to contact me by phone, mail, or email. They have since failed to provide any written validation or verification of the debt. I am requesting that the CFPB assist in having the collection agency either properly validate this debt or remove the inaccurate reporting from my credit files immediately due to their failure to provide proper notice.

### 14. 24520638 — gold=`service_fault` · model=`billing_charge`
I discovered a collection account being reported by Radius Global Solutions for {$910.00} on my credit report. I have no knowledge of this alleged debt, I do not know what it relates to, and I was never provided an initial collection notice informing me that this account had been placed for collection. As soon as I discovered this account, I contacted Radius Global Solutions and requested validation of the alleged debt. During that call, I was advised that the requested documentation would be mailed to me. As of today, I have still not received anything. If Radius Global Solutions claims that an initial notice or validation was mailed, I am r

### 15. 7448709 — gold=`service_fault` · model=`billing_charge`
Please update my account and remove the inaccurate late payment. I have always paid on time and never missed a payment. This is causing me a lot of stress and XXXX, and I can't even sleep properly because of this problem. I am begging you to update my account as soon as possible.

### 16. 7450437 — gold=`service_fault` · model=`billing_charge`
See the attached documents. I want the bureau to start the investigation on these accounts that I am never late for but they're reporting me as late.

### 17. 7450469 — gold=`service_fault` · model=`billing_charge`
Wells Fargo opened a personal loan answer credit card in my name without authorization. This been going on since XXXX XXXX, all these case numbers and XXXX numbers. I was supposed to be refunded {$6200.00} for unauthorized payments out of my checking account XXXX XXXX XXXX... I have received {$500.00} refunded but not the rest. I can't believe this situation in the times we are all in 2023. Wells Fargo made a huge mistake

### 18. 7450669 — gold=`service_fault` · model=`billing_charge`
XXXX XXXX XXXX XXXX XXXX XXXX, ME XXXX XX/XX/XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX, VA XXXX Capital One XXXX XXXX XXXX XXXX XXXX, VA XXXX Federal Trade Commission XXXX XXXX XXXX, XXXX. Washington XXXX DC XXXXXXXX XXXX XXXX credit card trip delay coverage Consumer Financial Protection Bureau 1700 G Street NW Washington, DC 20552 Dear Eclaimsline dba XXXX XXXX XXXX XXXX XXXX XXXX : On XX/XX/XXXX, I experienced an overnight trip delay while traveling on tickets purchased with my Capital One XXXX XXXX credit card. I incurred expenses totaling {$230.00} for 2 passengers. This card covers up to a maximum of XXXX XXXX doll

### 19. 7450993 — gold=`service_fault` · model=`billing_charge`
I have always made timely payments on this account, and it is deeply unjust that I am now facing consequences for something that is beyond my control. I kindly request an immediate update to my account and the removal of any inaccuracies that are causing me significant distress.

### 20. 7451012 — gold=`service_fault` · model=`billing_charge`
The company UPGRADE is claiming I owe XXXX on a XXXX line of credit that I never had access to. My information was fraudulently taken over after I applied and changed to an address and email I never consented nor submitted. That card was being used with out my permission hence that I never received it because the card had been high jacked and redirected to foreign addresses and emails. My information was stolen. I noticed many charges were taken out of my account on the dates listed below XXXX - {$.00} XXXX - {$890.00} XXXX - {$100.00} XXXX - {$910.00} XXXX - {$96.00} XXXX - {$95.00} I called UPGRADE and my bank to file a fraudulent claim to 

### 21. 7451352 — gold=`service_fault` · model=`billing_charge`
I've made several attempts to pay a charged off account with XXXX XXXX XXXX The amount of the charge off is {$2100.00}. Between yesterday and today I've made at least 10 phone calls and wasted hours of my time trying to resolve this account. The call I originally made they advised me that the account had been sold to XXXX XXXX XXXX and they gave me the phone number of XXXX to contact them. I contacted them yesterday and they advised me that they have nothing regarding this. Today I called XXXX again at XXXX and they provided the same information as I was provided yesterday. I expressed to them that I wanted to resolve this account and how cou

### 22. 7452822 — gold=`service_fault` · model=`billing_charge`
Credit inquiry received on XX/XX/2023 for a credit card with Capital One. This was not me. I immediately contacted Capital One and they said the account was not opened. However, Capital One has not reported this to XXXX even though they claim they sent he request. XXXX claims they have requested Capital One to respond to the false claim to remove from credit report but Capital One has not responded according to XXXX. I have waited 6 months to get this resolved and want this removed from my credit report immediately.

### 23. 7452911 — gold=`service_fault` · model=`billing_charge`
Portfolio RC XXXX XXXX This account was settled for less than the balance. The company updated the comments to show paid in full for less than the full balance but updated the actual balance to show the amount they discounted as due. This is preventing me from being able to purchase my home. I have requested for them to update to the actual balance and have no responses. I need this account to show the correct balance of XXXX.
