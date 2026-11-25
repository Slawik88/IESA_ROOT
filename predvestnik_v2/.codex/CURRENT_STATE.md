# ACTIVE — final exchange design wave, 2026-10-17

TECHNICAL RELEASE COMPLETE / LIVE. Owner authorised master+activation and initial
120000Mora issuance once. Production CLI executed on DO predvestnik-bot:
LOGURU_LEVEL=ERROR python predvestnik_v2/tools/release_coin_market_v2.py --prepare
--authorize-system-issuance-mora 120000 --enable. Response6coins,120000,flagsbothtrue.
Independent read-only prod SQL+verify:issuances1, gap_micro0, v2bothtrue/v1bothfalse,
secret_id7452b404e1ab2f30. Files under visualizations/2026/10/17/predvestnik-ui-ux-fixes:
exchange-production-activation.txt, -capital-audit.txt, -http.json(41PASS),
-boundary.json(8PASS), -version.json (d896JS8ac86e09672bca3ff64f matches),
-first-tick.png/.txt. REAL CRON verified: newpublishedtick22:15 andprice0.019988
without any production trade/quote advancing it. Market+creationquote read-only
UI on owner account works; no actual player purchase/creation executed.

Master through1ad7d996 (latestexactMoney6placesconfirmation+1алм. microcopy);
last knownhealthy deployd8965133dc5e-d5c3-4415-8de9-5b3fa57da88f. New1ad7autobuild
pending; publicactivation persists. Earlier release65aa59c45... firstserved.
Shared encrypted COIN_MARKET_V2_SECRET configured in DO, never output/storeplain.

USER LATEST: «Потом в конце проработай дизайн очень сильно биржи!!!! Это уже
в самом конце!» -> NOW finaldesignwave afterfunctionalrelease. UIonly, apply
UIUXProMax +ProductDesignaudit(existingcodetarget/screens; preflightnosavedcontext).
Readskills index/audit/user-context/critical-overrides; noFigma/Sites/newimagesneeded.

Read-onlycritic plan review highest priorities:
1 chart UTCaxis20:15 vslocalcaption22:15 mismatch ->consistenttimezone.
2 two-tickduplicatetimeandprice/gridlabeloverlap ->uniqueindices/collisionavoidance.
3 buy320twoprimarybuttons ->quotechecksecondaryafterpreview;restoreoninvalidate;
loadingfeedback +stalequote/pendingguardsmustremain.
4 compactmarketwallet170px/chipwrap ->earlierscannablecoins+refreshcaption.
5 portfoliolabelResultpositions, nottotalprofit; creatorcost0 excludescreation;
shortreceivedincludesreturnedcollateral, distinguishP&L.
6 one nativekeyboard chartcursor +touchscrubpan-y; preservefocusedselectedtick
onlivepoll, do notannouncecountdowneverysecond. Existingchart.attach alreadyhas
pointerevents (do not claim missingpointer). Addkeyboard/timeunification/legend.
Tariffs+0/7.5/20% referONLYstartingprice; preserveexistingform/economiccontracts.

ProposedUIplan: usefulportfolio summary+separatelong/shortsections/riskclosecards;
compactmarkethdr/searchsingle-linehscrollgroupchips (internalnotpageoverflow),
newstandfixturewithsyntheticlong+short+owncoinforQA, existingicons/tokensonly;
creation2visualfieldgroups withtariffcaptions; oneprimaryCTA; nativechartcursor.
Needauditfreshscreensandwritefindingsinexistingbacklog, implementthenNode/ASGI+
320/390/430/screenshots+critic, ONE finalpush/master+healthy/publicverification.

Tools/env: exchangeworktree C:/Users/makss/.codex/worktrees/predvestnik-exchange-v2/
IESA_ROOT branchcodex/exchange-v2. Currentgitcleanexceptuntrackedpredvestnik_v2/.codex.
Python F:/GitsRepos/IESA_ROOT/.venv/Scripts/python.exe; Node C:/Program Files/nodejs/node.exe.
LocalPG55438 DSNpostgresql://predvestnik_preprod@127.0.0.1:55438/predvestnik_preprod;
PGsuiteuniquedisposableschemas. Localstand8423 run_exchange_review.py outside repo
nowserveslatestbefore1ad7restartneededforcompiledassets; synthetic990000001fund5000
anddustholding1. No production fixture writes.

CUAbrowser2 persistent: liveMarketTab9 realprodcurrentlycoinORB, responsiveTab7
local, exchangeTab5userlocal, fixTab4userlocal, deployTab6DOconsole newpod
7985c57876-qxwbr cwd/workspace (projectnestedpredvestnik_v2); releaseStatusTab8DO
old65deploymentdetails butlatestbannerupdates. Owneradmintab1untouched.
IMPORTANTviewportcapappliesmostrecentlycreatedtab, nototherexistingtab! Lasttab9
currently390x844; resetbeforefinal. Needcreatefreshlocaltabforresponsiveifnecessary.
Console .xterm-screen locatorclick ->paste(null,cmd)->pressKey(null,Return), then
freshAX towaitresponse. AX terminaltext mayduplicatewrappedecho; actualresultsfine.
DOenvEditAXexposesothersecrets; avoidreopeningvars/fullAXthere. No needchangeenv.
Allscreenshotslocalmustabsoluteembedfinal; productionproofpreferfinalUI.

RootF:/checkoutdirtyunrelated, neveredit/reset. Reuse release_critic read-only.
