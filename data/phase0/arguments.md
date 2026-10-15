# Phase 0: 15 reference arguments for the Generative Philosophy Engine

Ground truth for grading LLM reconstruction + FOL formalization. Companion JSON: `phase0-arguments.json`. Premise-type tags: logical / definitional / empirical / normative, plus `metaphysical` (added: a-priori substantive principles fit none of the four). Each `fol_hint` is a sketch, not the only acceptable encoding.

All 15 reconstructions were machine-checked in Z3 5.3.0 (`verify.py` in same folder): the 12 valid ones (incl. induction) are consistent, entail C, and have NO redundant premise; Mill is consistent but not entailed (invalid); Sorites and Theseus premise sets are UNSAT (inconsistent). Induction is among those 12 and is question-begging by design.

## Coverage

| id | roles | expected | isomorphic_to |
|---|---|---|---|
| cogito | valid, tricky | valid (tricky-implicit-premise) | - |
| aristotle-function | valid, objection-target | valid | - |
| gettier-counterexample | valid, counterexample-form, objection-target | valid | - |
| epicurus-death | valid, objection-target | valid | - |
| singer-drowning-child | valid, objection-target | valid | - |
| kalam | valid, objection-target | valid | - |
| thomson-violinist | valid, analogical, objection-target | valid | - |
| epicurean-trilemma | valid, pair-A | valid | divine-hiddenness |
| divine-hiddenness | valid, pair-A | valid | epicurean-trilemma |
| hobbes-state-of-nature | valid, pair-B | valid | xunzi-origin-of-ritual |
| xunzi-origin-of-ritual | valid, pair-B | valid | hobbes-state-of-nature |
| sorites-heap | inconsistent, pair-C | inconsistent (premises-inconsistent, paradox) | ship-of-theseus-gradual |
| ship-of-theseus-gradual | inconsistent, pair-C | inconsistent (premises-inconsistent, paradox) | sorites-heap |
| mill-desirable | invalid, negative-control | invalid (equivocation, is-ought-gap, needs-unsupported-bridge) | - |
| induction-circular | valid, negative-control, question-begging | valid (question-begging, circular) | - |

Buckets: VALID core = cogito, aristotle-function, gettier-counterexample, epicurus-death, singer-drowning-child (+ kalam, thomson, trilemma, hiddenness, hobbes, xunzi are also valid). OBJECTION library = epicurus-death, kalam, singer-drowning-child, thomson-violinist, aristotle-function, plus gettier and the two pair-A args. PAIRS = A, B, C below. NEGATIVE controls = mill-desirable (invalid), induction-circular (question-begging). Inconsistent positive controls = sorites-heap, ship-of-theseus-gradual.

## Expected isomorphic pairs

**Pair A: epicurean-trilemma <-> divine-hiddenness**
- Mapping: Gratuitous(e) <-> NonresistantNonbelief(b); PerfGood <-> PerfLoving; Omni, God, Able, Will, Occurs identical. Same 5-premise modus-tollens skeleton: God->(Omni&Q); Omni->able(all X); Q->willing(all X); able&willing->~occurs; some X occurs; so ~God.
- Caveat: Different content of X (suffering vs. nonbelief); both fail identically if P5 is denied.

**Pair B: hobbes-state-of-nature <-> xunzi-origin-of-ritual**
- Mapping: Des<->Des; Scarce<->Limited; Rivals<->Contend; NoCommonPower<->NoRitualMeasure; War<->Chaos(luan); Miserable<->Destitute. Skeleton: shared desire for scarce good -> conflict; conflict & no ordering authority -> disorder; disorder -> misery; so misery absent authority.
- Caveat: Real texts differ in remedy (Leviathan/contract vs. ritual/moral cultivation); core competition argument is isomorphic.

**Pair C: sorites-heap <-> ship-of-theseus-gradual**
- Mapping: Heap(10000-k) <-> Same(k) (index reversal); tolerance step <-> one-plank tolerance; ~Heap(1) <-> ~Same(N). Skeleton: base, tolerance step, contradicting endpoint (inconsistent triad).
- Caveat: Both expected UNSAT at check (a); cross-tradition matching should put them in one class despite different subject matter.

**Weak isomorphs (false-friend test, should match only at trivial skeleton level):** cogito, kalam, induction-circular all share `forall x(A(x)->B(x)), A(c) |- B(c)`. A good matcher should NOT rank them with the strong pairs above.

**Shared-premise library hits:** epicurus-death.P2 is accepted by Nagel (attacks P1); kalam P1 and P2 are attacked by Hume and Kant respectively; epicurean-trilemma P1-P4 are shared with divine-hiddenness up to renaming (definitional core of 'God').

## Arguments

### cogito: Cogito (Descartes)
- Roles: valid, tricky
- Source: Rene Descartes, Meditations on First Philosophy II (1641); Principles of Philosophy I.7 (1644)
- Source text: "I think, therefore I am" (Principles I.7, Latin: cogito, ergo sum). Descartes (Second Replies) denies it is a syllogism; the major premise is implicit.
- Expected verdict: **valid** (flags: tricky-implicit-premise)

  - P1 [implicit] (metaphysical): Whatever thinks exists.  `forall x. Thinks(x) -> Exists(x)`
  - P2 (empirical): I am thinking.  `Thinks(i)   [introspective datum]`
  - C: I exist.  [Exists(i)]
- Notes / why FOL suffices: Skeleton = universal instantiation + modus ponens (all 2-premise 'forall x (A->B), A(c) |- B(c)'). Pitfall: Exists as a predicate vs. FOL's built-in existence (free-logic issue; 'exists x. x=i' is a theorem of classical FOL so a naive encoding makes the conclusion trivially true). Grade: LLM must (1) flag P1 as implicit, (2) NOT encode C as exists x. x=i without noting triviality. FOL suffices: one monadic predicate pair and one constant.

### aristotle-function: Function argument (Aristotle)
- Roles: valid, objection-target
- Source: Aristotle, Nicomachean Ethics I.7, 1097b22-1098a18
- Source text: Paraphrase: the good of a flute-player, sculptor or any craftsman lies in their function; so too for a human, whose function is activity of soul according to reason.
- Expected verdict: **valid**

  - P1 (normative): For any kind with a characteristic function, a member of that kind does well (has its good) exactly when it performs that function excellently.  `forall x,k,f. Kind(k)&Func(k,f)&Mem(x,k) -> (GoodFor(x,f) <-> Exc(x,f))`
  - P2 (metaphysical): Human beings have some characteristic function.  `exists f. Func(Human,f)`
  - P3 (definitional): The only characteristic function of human beings is rational activity of the soul.  `forall f. Func(Human,f) -> f = RA`
  - P4 [implicit] (definitional): Human beings are a kind (species).  `Kind(Human)`
  - C: For every human, doing well consists in performing rational activity excellently.
- Objection aristotle-function.O1: Bernard Williams (Ethics and the Limits of Philosophy (1985), ch.3; also Hume-style is-ought worry) -> deny P1: Doing a kind's function well does not by itself fix an individual's good (a good assassin performs a function well); the function-to-good bridge is unsupported. Shared: P2, P3
- Notes / why FOL suffices: Z3-verified: all 4 premises needed (P4 and the existence premise P2 are the usual LLM omissions; without P2 the conclusion is vacuous). Kinds are reified as individuals so no second-order logic is needed. FOL suffices: dyadic relations over a sort of kinds/individuals.

### gettier-counterexample: Gettier case against JTB
- Roles: valid, counterexample-form, objection-target
- Source: Edmund Gettier, Is Justified True Belief Knowledge?, Analysis 23(6), 1963
- Source text: Paraphrase: Smith has strong evidence for e (Jones will get the job and has ten coins), deduces f (the man who gets the job has ten coins); f is true only because Smith gets the job. Smith does not know f.
- Expected verdict: **valid**

  - P1 (empirical): Smith believes f, having competently deduced it from e.  `Bel(smith,f) & Ded(smith,f,e)`
  - P2 [implicit] (definitional): Justification is transmitted across competent deduction: if S is justified in p and deduces q from p, S is justified in q.  `forall s,p,q. J(s,p)&Ded(s,q,p) -> J(s,q)`
  - P3 (empirical): Smith is justified in believing e.  `J(smith,e)`
  - P4 (empirical): f is true.  `T(f)`
  - P5 (empirical): Smith does not know f.  `~K(smith,f)   [an intuition about the case; tag as intuition]`
  - C: It is not the case that, for all S and p, justified true belief that p suffices for S's knowing that p.
- Objection gettier-counterexample.O1: Weinberg, Nichols & Stich (Normativity and Epistemic Intuitions, Philosophical Topics 29 (2001)) -> deny/undercut P5: The no-knowledge verdict is a culturally variable intuition, not a datum. Shared: P1, P2, P3, P4
- Notes / why FOL suffices: Counterexample form: instance contradicts a universal (the JTB analysis), so the target analysis appears only in C, never as a premise. Z3-verified, no redundant premise. Watch for LLMs that put the JTB analysis in as a premise (then the set is inconsistent). FOL suffices: universal vs instance.

### epicurus-death: Death is nothing to us (Epicurus)
- Roles: valid, objection-target
- Source: Epicurus, Letter to Menoeceus, sec. 124-125 (via Diogenes Laertius X)
- Source text: "Death is nothing to us" (sec. 125); good and evil consist in sensation, and death is the privation of sensation.
- Expected verdict: **valid**

  - P1 (normative): Whatever is good or bad for a person involves that person's sensation.  `forall e,x. (GoodFor(e,x)|BadFor(e,x)) -> Sens(e,x)`
  - P2 (empirical): Death involves no sensation for the one who dies.  `forall e,x. Death(e,x) -> ~Sens(e,x)`
  - C: Death is neither good nor bad for the one who dies.
- Objection epicurus-death.O1: Thomas Nagel (Death, Nous 4 (1970); reprinted in Mortal Questions) -> deny P1: Some things are bad for a person without involving their sensation (betrayal never discovered); death is bad as deprivation of the goods life would have held. Shared: P2
- Notes / why FOL suffices: Skeleton: forall(A->B), forall(C->~B) |- forall(C->~A) (Camestres). Nagel ACCEPTS P2 and attacks P1: the canonical shared-premise/attacked-premise test. FOL suffices: monadic/dyadic predicates, no modality.

### singer-drowning-child: Famine, affluence and morality (Singer)
- Roles: valid, objection-target
- Source: Peter Singer, Famine, Affluence, and Morality, Philosophy & Public Affairs 1(3), 1972
- Source text: Paraphrase: if we can prevent something bad without sacrificing anything of comparable moral importance, we ought to; analogized by a child drowning in a shallow pond.
- Expected verdict: **valid**

  - P1 (normative): Suffering and death from lack of food are bad.  `forall e. Famine(e) -> Bad(e)`
  - P2 (normative): If one can prevent something bad without sacrificing anything of comparable moral importance, one ought to do so.  `forall a,e. Bad(e)&CanPrevent(a,e)&~Sacr(a,e) -> Ought(a,e)`
  - P3 (empirical): There is some such famine suffering that we can prevent without sacrificing anything of comparable moral importance.  `exists e. Famine(e)&CanPrevent(we,e)&~Sacr(we,e)`
  - C: We ought to prevent some famine suffering.
- Objection singer-drowning-child.O1: Bernard Williams (A Critique of Utilitarianism, in Utilitarianism: For and Against (1973)) -> deny P2: P2 generalizes to a demand that overrides each agent's integral personal projects; a principle with that consequence cannot be a moral requirement. Shared: P1, P3
- Notes / why FOL suffices: Z3-verified minimal. The 'drowning child' analogy is a separate intuition-pump supporting P2, not a premise of the core argument; do not require it. Shares the 'bad + can prevent -> ought' pattern with epicurean-trilemma only loosely. FOL suffices: one existential witness plus two universals.

### kalam: Kalam cosmological argument
- Roles: valid, objection-target
- Source: al-Ghazali (and later W. L. Craig), al-Iqtisad fi'l-I'tiqad (c.1095), on the temporal origination of the world
- Source text: Paraphrase: whatever begins to exist has a cause of its beginning; the world began to exist; so the world has a cause.
- Expected verdict: **valid**

  - P1 (metaphysical): Everything that begins to exist has a cause.  `forall x. Begins(x) -> exists y. Causes(y,x)`
  - P2 (empirical): The universe began to exist.  `Begins(univ)`
  - C: The universe has a cause.
- Objection kalam.O1: David Hume (A Treatise of Human Nature I.iii.3) -> deny P1: That every beginning needs a cause is neither intuitively nor demonstratively certain. Shared: P2
- Objection kalam.O2: Immanuel Kant (Critique of Pure Reason, First Antinomy) -> deny P2: Reason can equally argue that the world has no beginning in time. Shared: P1
- Notes / why FOL suffices: Two objections hitting different premises (P1 vs P2) make this ideal for premise-level library tests. Pure UI+MP; skeleton is shared with cogito and the induction argument (weak isomorphs; should be distinguished by the matcher from the strong pairs by size/shape only trivially). 'Causes' is not temporal; 'begins to exist' is left as primitive.

### thomson-violinist: The violinist (Thomson)
- Roles: valid, analogical, objection-target
- Source: Judith Jarvis Thomson, A Defense of Abortion, Philosophy & Public Affairs 1(1), 1971
- Source text: Paraphrase: you wake plugged into a famous violinist who needs your kidneys for nine months; you are not thereby required to stay connected; pregnancy from rape is relevantly similar.
- Expected verdict: **valid**

  - P1 (metaphysical): Suppose, for the sake of argument, that the fetus is a person.  `Person(fetus)   [concession, not endorsement]`
  - P2 (normative): A person's right to life does not include a right to use another person's body when the other has not granted that use (generalized from the violinist case).  `forall x,y. Person(x)&Person(y)&Need(x,y)&~Granted(y,x) -> ~RightUse(x,y)`
  - P3 (empirical): In pregnancy from rape the fetus needs the woman's body and she has not granted its use.  `Need(fetus,woman) & ~Granted(woman,fetus)`
  - P4 [implicit] (definitional): The woman is a person.  `Person(woman)`
  - P5 [implicit] (normative): If x has no right to use y's body, then it is permissible for y to detach from x.  `forall x,y. ~RightUse(x,y) -> PermDetach(y,x)`
  - C: It is permissible for the woman to detach from (abort) the fetus.
- Objection thomson-violinist.O1: Francis Beckwith / John Finnis (Politically Correct Death (1993); The Rights and Wrongs of Abortion, PPA 2(2), 1973) -> deny/undercut P5: Detaching the violinist is letting die; abortion is killing, and parental responsibility differs from stranger-obligation, so permissibility does not transfer. Shared: P1, P2, P3
- Notes / why FOL suffices: Real argument is analogical; the flattened FOL form puts the analogy's work into generalized P2 plus implicit bridge P5. Z3-verified minimal on this reconstruction. A faithful LLM may legitimately choose a different decomposition (e.g. with an explicit similarity premise); grade on whether the analogical step is made an explicit premise, not on exact wording. Sensitive topic; used strictly as academic example.

### epicurean-trilemma: Epicurean trilemma / problem of evil
- Roles: valid, pair-A
- Source: Epicurus as reported by Hume (Philo); formal refinements by Mackie, Rowe, David Hume, Dialogues Concerning Natural Religion, Part X (1779)
- Source text: "Is he willing to prevent evil, but not able?" (Part X, after Epicurus).
- Expected verdict: **valid**

  - P1 (definitional): If any being is God, it is omnipotent and perfectly good.  `forall x. God(x) -> Omni(x)&PerfGood(x)`
  - P2 [implicit] (definitional): An omnipotent being is able to prevent any gratuitous evil.  `forall x. Omni(x) -> forall e. Grat(e) -> Able(x,e)`
  - P3 (normative): A perfectly good being is willing to prevent any gratuitous evil.  `forall x. PerfGood(x) -> forall e. Grat(e) -> Will(x,e)`
  - P4 [implicit] (metaphysical): What a being is both able and willing to prevent does not occur.  `forall x,e. Able(x,e)&Will(x,e)&Grat(e) -> ~Occurs(e)`
  - P5 (empirical): Some gratuitous evil occurs.  `exists e. Grat(e)&Occurs(e)`
  - C: There is no God.  [~exists x. God(x)]
- Objection epicurean-trilemma.O1: Stephen Wykstra / skeptical theists (The Humean Obstacle to Evidential Arguments from Suffering, Int. J. Phil. Religion 16 (1984)) -> undercut P5: Our inability to see a justifying reason for an evil is poor evidence that none exists. Shared: P1, P2, P3, P4
- Notes / why FOL suffices: Hume's original lacks the 'gratuitous' restriction (needed for validity: Rowe's repair), so P2/P3 are scoped to gratuitous evil. Mackie's version (omnipotence + goodness + evil + 'good eliminates evil as far as it can') is the same triad stated as an INCONSISTENT set; here it is re-cast as a modus-tollens refutation. Both framings should be accepted. Z3-verified minimal.

### divine-hiddenness: Divine hiddenness (Schellenberg)
- Roles: valid, pair-A
- Source: J. L. Schellenberg, Divine Hiddenness and Human Reason (Cornell UP, 1993), ch.1
- Source text: Paraphrase: a perfectly loving God would make a personal relationship with Himself possible for any creature capable of it and not resisting; there are such non-resistant non-believers.
- Expected verdict: **valid**

  - P1 (definitional): If any being is God, it is omnipotent and perfectly loving.  `forall x. God(x) -> Omni(x)&PerfLoving(x)`
  - P2 [implicit] (definitional): An omnipotent being is able to prevent any case of non-resistant nonbelief.  `forall x. Omni(x) -> forall b. NRNB(b) -> Able(x,b)`
  - P3 (normative): A perfectly loving being is willing to prevent any case of non-resistant nonbelief.  `forall x. PerfLoving(x) -> forall b. NRNB(b) -> Will(x,b)`
  - P4 [implicit] (metaphysical): What a being is both able and willing to prevent does not occur.  `forall x,b. Able(x,b)&Will(x,b)&NRNB(b) -> ~Occurs(b)`
  - P5 (empirical): Some non-resistant nonbelief occurs.  `exists b. NRNB(b)&Occurs(b)`
  - C: There is no God.
- Objection divine-hiddenness.O1: Paul Moser / Michael Murray (Moser, The Elusive God (2008); Murray, Coercion and the Hiddenness of God, APQ 30 (1993)) -> deny P3: Love may permit hiddenness (to preserve freedom, or to invite moral/volitional transformation), so willingness to prevent nonbelief does not follow. Shared: P1, P2, P4
- Notes / why FOL suffices: Schellenberg's own statement has more steps (openness to relationship -> belief). Flattened here to the same 5-premise skeleton as the trilemma, which is the point of the pair. Grader should accept a longer faithful reconstruction as long as an LLM does not silently drop the omnipotence/ability premise.

### hobbes-state-of-nature: State of nature as war (Hobbes)
- Roles: valid, pair-B
- Source: Thomas Hobbes, Leviathan, ch. XIII (1651)
- Source text: "solitary, poor, nasty, brutish, and short"; "if any two men desire the same thing... they become enemies".
- Expected verdict: **valid**

  - P1 (definitional): If two distinct persons desire the same good and cannot both enjoy it, they become rivals.  `forall x,y,g. Des(x,g)&Des(y,g)&Scarce(g)&x!=y -> Riv(x,y)`
  - P2 (empirical): In the natural condition there are two distinct persons who desire the same scarce good.  `exists x,y,g. Des(x,g)&Des(y,g)&Scarce(g)&x!=y`
  - P3 (empirical): Rivals with no common power to keep them in awe are at war.  `forall x,y. Riv(x,y)&NoCP -> War(x,y)`
  - P4 [implicit] (definitional): In the natural condition there is no common power.  `NoCP`
  - P5 (empirical): Those at war live miserable lives.  `forall x,y. War(x,y) -> Mis(x)&Mis(y)`
  - C: In the natural condition some persons live miserable lives.
- Notes / why FOL suffices: Hobbes' full argument adds diffidence/glory as separate causes of quarrel; this core is the competition strand. Z3-verified minimal. Wording of C is deliberately weak (existential); Hobbes' 'all' needs an extra universal premise about equality.

### xunzi-origin-of-ritual: Origin of ritual (Xunzi)
- Roles: valid, pair-B
- Source: Xunzi, Xunzi, ch. 19 'Discourse on Ritual' (Li lun), opening; cf. ch. 23 'Human nature is bad'
- Source text: "人生而有欲" (people are born with desires); unmet desire seeks, unmeasured seeking breeds contention, contention disorder, disorder poverty.
- Expected verdict: **valid**

  - P1 (empirical): If two distinct people desire the same good that is limited, they come to contend.  `forall x,y,g. Des(x,g)&Des(y,g)&Limited(g)&x!=y -> Contend(x,y)`
  - P2 (empirical): There are two distinct people who desire the same limited good.  `exists x,y,g. Des(x,g)&Des(y,g)&Limited(g)&x!=y`
  - P3 (empirical): Contenders with no ritual apportioning measure fall into disorder.  `forall x,y. Contend(x,y)&NoRitual -> Chaos(x,y)`
  - P4 [implicit] (definitional): Prior to the sage kings' ritual there is no apportioning measure.  `NoRitual`
  - P5 (empirical): Those in disorder are impoverished.  `forall x,y. Chaos(x,y) -> Dest(x)&Dest(y)`
  - C: Without ritual, some people are impoverished.
- Notes / why FOL suffices: Real text then concludes the Former Kings instituted ritual to apportion goods (a normative/functional claim); omitted here so the core matches Hobbes' skeleton. Translations: Watson (1963), Hutton (2014), Knoblock; none PD, so paraphrase only. Note Mencius 6A is the opposing view and not an isomorph.

### sorites-heap: Sorites paradox (Eubulides)
- Roles: inconsistent, pair-C
- Source: Eubulides of Miletus, reported in Cicero, Academica II.49; Diogenes Laertius II.108
- Source text: Paraphrase: one grain is not a heap; adding one grain never makes a heap; yet enough grains make a heap.
- Expected verdict: **inconsistent** (flags: premises-inconsistent, paradox)

  - P1 (empirical): A pile of 10000 grains is a heap.  `Heap(10000)   (Z3 test used 10)`
  - P2 (definitional): Tolerance: removing one grain from a heap leaves a heap.  `forall n. n>=2 & Heap(n) -> Heap(n-1)`
  - P3 (definitional): A single grain is not a heap.  `~Heap(1)`
  - C: A single grain is a heap.  [Heap(1)]
- Notes / why FOL suffices: Z3 (LIA, quantifier) returns UNSAT on the premises for N=10, but UNKNOWN for N=10000 because of quantifier+deep instantiation; recommend N<=20 or explicit unrolling. {P1,P2} entail C (valid) but P3 contradicts C: expected check (a) FAILS. A 'finite chain' without numbers needs transitive closure, which is not FOL-definable; use integers (LIA) or a constant chain. This is the designed 'consistency check fires' positive control; the minimality result is meaningless on an inconsistent set.

### ship-of-theseus-gradual: Ship of Theseus (gradual replacement)
- Roles: inconsistent, pair-C
- Source: Plutarch, Life of Theseus 23.1 (c.100 CE)
- Source text: Paraphrase: the Athenians preserved Theseus' ship, replacing decayed timbers one by one; philosophers disputed whether it was still the same ship.
- Expected verdict: **inconsistent** (flags: premises-inconsistent, paradox)

  - P1 (definitional): With no planks replaced, the ship is the original ship.  `Same(0)`
  - P2 (metaphysical): Tolerance: replacing a single plank of a ship that is the original leaves it the original.  `forall n. 0<=n<N & Same(n) -> Same(n+1)`
  - P3 (metaphysical): A ship with every one of the N planks replaced is not the original ship.  `~Same(N)`
  - C: The ship with all N planks replaced is the original ship.  [Same(N)]
- Notes / why FOL suffices: Plutarch states the puzzle, not this formalization; this is the gradual-replacement sorites reading. Z3-verified UNSAT for N=10. Mapping to Sorites: Heap(10000-k) <-> Same(k) (index reversed): base, tolerance step, contradicting endpoint.

### mill-desirable: Proof of utility: 'desired' to 'desirable' (Mill)
- Roles: invalid, negative-control
- Source: John Stuart Mill, Utilitarianism, ch. IV (1863)
- Source text: "people do actually desire it" (ch. IV); evidence that something is desirable is that it is desired.
- Expected verdict: **invalid** (flags: equivocation, is-ought-gap, needs-unsupported-bridge)

  - P1 (empirical): People desire happiness as an end.  `Desired(happiness)&AsEnd(happiness)`
  - P2 (empirical): People desire nothing besides happiness as an end.  `forall x. Desired(x)&AsEnd(x) -> x=happiness`
  - C: Happiness is the only thing desirable as an end.  [forall x. Desirable(x)&AsEnd(x) -> x=happiness]
- Notes / why FOL suffices: Z3: premises consistent, conclusion NOT entailed (countermodel exists). It becomes valid only with the bridge forall x. Desirable(x) <-> Desired(x), which is exactly the contested step (visible:seen / desirable:desired analogy; Moore and others call it an equivocation on '-able'). GRADING: LLM passes iff it either leaves the argument invalid or adds the bridge as an explicitly flagged [implicit] controversial premise; fails if it silently adds the bridge. Same family as Hume's is-ought gap.

### induction-circular: Circular justification of induction (Hume)
- Roles: valid, negative-control, question-begging
- Source: David Hume, An Enquiry concerning Human Understanding, sec. IV (1748); Treatise I.iii.6
- Source text: Paraphrase: to argue that induction will succeed because it has succeeded presupposes the uniformity of nature, the thing in question.
- Expected verdict: **valid** (flags: question-begging, circular)

  - P1 (empirical): Induction has succeeded in the past.  `SucceededPast(induction)`
  - P2 [implicit] (metaphysical): Methods that have succeeded in the past will succeed in the future (uniformity principle).  `forall x. SucceededPast(x) -> SucceedsFuture(x)`
  - C: Induction will succeed in the future.
- Notes / why FOL suffices: Formally valid, consistent, minimal, and C is not a premise verbatim, so Z3 checks (a)-(d) ALL PASS. The defect (P2 is the principle whose justification is at issue; C is a direct instance of it) is not formally detectable: this control deliberately probes the limit of the pipeline and should be reported as 'passes formal checks, flagged question-begging by judge/human'. Candidate heuristic for check (d): flag when C is a one-step instance of a universal premise derived from the same method it concludes about.
