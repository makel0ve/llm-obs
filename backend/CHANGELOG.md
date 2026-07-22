# CHANGELOG


## v0.44.4 (2026-07-22)

### Bug Fixes

- Store small payloads in object storage
  ([`bf17729`](https://github.com/makel0ve/llm-obs/commit/bf17729218c4abfabf3031d0c71dbabb711fc9cc))

### Chores

- Trigger ci for release sync
  ([`b76ec3d`](https://github.com/makel0ve/llm-obs/commit/b76ec3d9552d7083b7d43bdd477309b2eebd2818))

### Documentation

- Decide pricing tenancy model
  ([`6361bcb`](https://github.com/makel0ve/llm-obs/commit/6361bcbeba6aac101687b51ea502b8af802b7a77))

### Testing

- Enforce payload privacy invariants
  ([`cb8d4a9`](https://github.com/makel0ve/llm-obs/commit/cb8d4a9ac8a71dec89aec0989dc92cab5f19b18e))


## v0.44.3 (2026-07-22)

### Chores

- Trigger ci for release sync
  ([`96d4748`](https://github.com/makel0ve/llm-obs/commit/96d474811f9ae673cc51c28fd33eabb53a1ccac3))

### Performance Improvements

- Reuse pricing lookups within span batches
  ([`6b8346a`](https://github.com/makel0ve/llm-obs/commit/6b8346a6fbf2645cb9c0d6eeaaab07eeac7d2461))


## v0.44.2 (2026-07-22)

### Bug Fixes

- Cache pricing by active interval
  ([`adc3f8f`](https://github.com/makel0ve/llm-obs/commit/adc3f8f1dafddc1bb33da360874e460d4fc5d74c))

### Chores

- Trigger ci for release sync
  ([`d29b8af`](https://github.com/makel0ve/llm-obs/commit/d29b8af0cbd22c120b5740405fe28a765993bd88))

### Testing

- Cover pricing boundary lookups
  ([`ceac5e5`](https://github.com/makel0ve/llm-obs/commit/ceac5e5416d25b208fcb705f9096c7dc656601c0))


## v0.44.1 (2026-07-22)

### Bug Fixes

- **sdk**: Derive user agent from package version
  ([`baa54d7`](https://github.com/makel0ve/llm-obs/commit/baa54d7c04ab0c1d9fe23fd894599016fe763dbe))

### Chores

- Trigger ci for release sync
  ([`feeec6a`](https://github.com/makel0ve/llm-obs/commit/feeec6a9a61d12e3ae4115e2182fa1bd094194d2))


## v0.44.0 (2026-07-21)

### Chores

- Trigger ci for release sync
  ([`2b4b1ae`](https://github.com/makel0ve/llm-obs/commit/2b4b1ae1860075f469cd3d7aee53d36e18e8cbbc))

### Features

- Expose sdk drop diagnostics
  ([`15fd681`](https://github.com/makel0ve/llm-obs/commit/15fd681ef806380e9df91ceaabb3d8c40c0ab86e))


## v0.43.0 (2026-07-21)

### Chores

- Trigger ci for release sync
  ([`167e476`](https://github.com/makel0ve/llm-obs/commit/167e4764977802a6b2e2af0065a0e9c370725b6e))

### Features

- Instrument sdk provider streams
  ([`e41cbb8`](https://github.com/makel0ve/llm-obs/commit/e41cbb8c208190d1f53ed96e72efc5ae6aac938d))


## v0.42.20 (2026-07-21)

### Bug Fixes

- Make sdk provider patching idempotent
  ([`17fc902`](https://github.com/makel0ve/llm-obs/commit/17fc9027c70bf4a124b85448254d67e58a807fbd))

### Chores

- Trigger ci for release sync
  ([`c06d967`](https://github.com/makel0ve/llm-obs/commit/c06d967427436ca7e6df517fa21cf124084c3fe2))


## v0.42.19 (2026-07-21)

### Bug Fixes

- Harden sdk async lifecycle
  ([`d01fc8b`](https://github.com/makel0ve/llm-obs/commit/d01fc8b6bdfcbeb913f727acd0f1861327bc6130))

### Chores

- Trigger ci for release sync
  ([`96ee192`](https://github.com/makel0ve/llm-obs/commit/96ee19268ee478f187a33e61314e804c32933ab3))


## v0.42.18 (2026-07-21)

### Bug Fixes

- Add sdk idempotency key per batch
  ([`debaa76`](https://github.com/makel0ve/llm-obs/commit/debaa760a178876ed037fc338655ca4578ad88cf))

### Chores

- Trigger ci for release sync
  ([`a19418b`](https://github.com/makel0ve/llm-obs/commit/a19418b3eee734f3c759459dea5915525f6307ac))


## v0.42.17 (2026-07-21)

### Bug Fixes

- Split sdk active and failed flush buffers
  ([`ffe0e2f`](https://github.com/makel0ve/llm-obs/commit/ffe0e2f2711153645abfb641645135d1d1049944))

### Chores

- Trigger ci for release sync
  ([`5e0e8ea`](https://github.com/makel0ve/llm-obs/commit/5e0e8eaa6dcacda914b55de56f002b563c6771f4))

### Testing

- Add existing database migration smoke
  ([`ea68c3d`](https://github.com/makel0ve/llm-obs/commit/ea68c3da7dbf8ed853a92389c607a9de216c313d))

- Add sdk buffer failure baseline
  ([`b53f57b`](https://github.com/makel0ve/llm-obs/commit/b53f57b806e4949e3f94ee2dc924c0e28a6b65b0))


## v0.42.16 (2026-07-21)

### Bug Fixes

- Automate future trace partitions
  ([`e85a0c4`](https://github.com/makel0ve/llm-obs/commit/e85a0c43b84cab37764f32a1f97e3e7a29dc19ad))

### Chores

- Trigger ci for release sync
  ([`1750c7b`](https://github.com/makel0ve/llm-obs/commit/1750c7bcfa656f9042824baec903e2701ae68796))

### Documentation

- Add partition pruning audit
  ([`767501a`](https://github.com/makel0ve/llm-obs/commit/767501a5c8d8463713c5383679ded6435082374c))


## v0.42.15 (2026-07-21)

### Bug Fixes

- Delete retention spans by composite key
  ([`e3ef684`](https://github.com/makel0ve/llm-obs/commit/e3ef684af5939935791d97600f08058d15095a65))

### Chores

- Trigger ci for release sync
  ([`3772ee9`](https://github.com/makel0ve/llm-obs/commit/3772ee97d888a5eaebcf01d9f642147836166036))

### Documentation

- Document telemetry delivery guarantees
  ([`560e9da`](https://github.com/makel0ve/llm-obs/commit/560e9dadb6cd999904fd16e122893a023269d171))

### Testing

- Cover retention composite key regression
  ([`4536f5b`](https://github.com/makel0ve/llm-obs/commit/4536f5bb153494f0d37c194b333090c83a14f3ca))


## v0.42.14 (2026-07-20)

### Bug Fixes

- Add transactional outbox foundation
  ([`0f7a904`](https://github.com/makel0ve/llm-obs/commit/0f7a9048c4d872b17ed630c57693d12ea9ae84c2))

- Add transactional outbox foundation
  ([`80f8c21`](https://github.com/makel0ve/llm-obs/commit/80f8c21c82564b9c3a3c2637abaad149403a5e26))

### Chores

- Trigger ci for release sync
  ([`2c7fb3a`](https://github.com/makel0ve/llm-obs/commit/2c7fb3aea45ad36ece9159685a008f0e40b0ae77))


## v0.42.13 (2026-07-20)

### Bug Fixes

- Add durable idempotency state machine
  ([`b676ff2`](https://github.com/makel0ve/llm-obs/commit/b676ff23ceaeabc3c94ea7ee9954d269079f35c6))

### Chores

- Trigger ci for release sync
  ([`cbc743a`](https://github.com/makel0ve/llm-obs/commit/cbc743a7377f3156f6140d2d0e3529468577f09f))


## v0.42.12 (2026-07-20)

### Bug Fixes

- Classify worker transient errors
  ([`7dbf635`](https://github.com/makel0ve/llm-obs/commit/7dbf635018b6eba2b9e6ee66673f361f5c9caf38))

### Chores

- Trigger ci for release sync
  ([`83f34b3`](https://github.com/makel0ve/llm-obs/commit/83f34b359e549f9effcaedb5f42916c104eb9b76))


## v0.42.11 (2026-07-20)

### Bug Fixes

- Make worker span trace writes atomic
  ([`85e82a2`](https://github.com/makel0ve/llm-obs/commit/85e82a24258e7f650d809b3b39447155f7573c24))

### Chores

- Ignore local planning files
  ([`ce45783`](https://github.com/makel0ve/llm-obs/commit/ce45783b5d75d3c8b8d19ea268c3b25dfc364375))

- Trigger ci for release sync
  ([`eb1a2fa`](https://github.com/makel0ve/llm-obs/commit/eb1a2fa8da1a54976e2053a4305ecd68f56398a2))

### Testing

- Add worker failure injection baseline
  ([`65fa8ef`](https://github.com/makel0ve/llm-obs/commit/65fa8ef1ee8c4a21620056721645a2b248807aa8))


## v0.42.10 (2026-07-20)

### Bug Fixes

- Restrict metrics and readiness exposure
  ([`f793f16`](https://github.com/makel0ve/llm-obs/commit/f793f16e634a1a2a7ab764aa04c7cc9b5f032daf))

### Chores

- Harden production healthchecks
  ([`c6b366d`](https://github.com/makel0ve/llm-obs/commit/c6b366d8477e683f70ea5e7d522b2915de701517))

- Pin production images
  ([`3e2a3af`](https://github.com/makel0ve/llm-obs/commit/3e2a3af9a2597b9bb90bc3074b0334fd9532c140))

- Restrict production service exposure
  ([`5c22dac`](https://github.com/makel0ve/llm-obs/commit/5c22dacbbd609d4e41d77a156184af50dcf6e9af))

- Trigger ci for release sync
  ([`5e13de8`](https://github.com/makel0ve/llm-obs/commit/5e13de82b2280ae9f5d1a9b6ae2f28225f53f29e))

### Documentation

- Decide browser token storage
  ([`907fcf4`](https://github.com/makel0ve/llm-obs/commit/907fcf49a0db2a5afa822a45da84c6c0e9c2a3a1))

### Testing

- Expand audit regression coverage
  ([`d12ae05`](https://github.com/makel0ve/llm-obs/commit/d12ae0513c892409b61bf29982bf555871ccb571))


## v0.42.9 (2026-07-20)

### Bug Fixes

- Reconnect sse streams
  ([`51990f7`](https://github.com/makel0ve/llm-obs/commit/51990f7e728700a02dfc6ce4f08a93b1652d1cf3))

### Chores

- Trigger ci for release sync
  ([`0650021`](https://github.com/makel0ve/llm-obs/commit/06500219b6ac69004f0cdcd7c283526b7e39490b))

### Documentation

- Align ingest endpoint references
  ([`c6012ee`](https://github.com/makel0ve/llm-obs/commit/c6012eec788331f96c7b05573f10b95cf669b5e1))


## v0.42.8 (2026-07-20)

### Bug Fixes

- Make audit logging consistency explicit
  ([`0cc4493`](https://github.com/makel0ve/llm-obs/commit/0cc44930f8564a24f9e3f95ed09d67174667cb7b))

### Chores

- Trigger ci for release sync
  ([`db01e99`](https://github.com/makel0ve/llm-obs/commit/db01e99aa7f27bcc4a39562594629226dd4e477d))


## v0.42.7 (2026-07-19)

### Bug Fixes

- Report accurate batch insert counts
  ([`c96da9e`](https://github.com/makel0ve/llm-obs/commit/c96da9e983ba74f7282b7fb09fad075af01416bb))

### Chores

- Trigger ci for release sync
  ([`0d58aa7`](https://github.com/makel0ve/llm-obs/commit/0d58aa7f114aa0864c89788acc78b0714ed62f55))


## v0.42.6 (2026-07-17)

### Bug Fixes

- Reserve idempotency keys atomically
  ([`6e0f9db`](https://github.com/makel0ve/llm-obs/commit/6e0f9dbe09290194549ba80a5f2818783d3714f4))

### Chores

- Trigger ci for release sync
  ([`0e5a740`](https://github.com/makel0ve/llm-obs/commit/0e5a740d6e2ddd36be2971009e8961775ba22f4a))


## v0.42.5 (2026-07-17)

### Bug Fixes

- Route final task failures to dlq
  ([`a35b3f4`](https://github.com/makel0ve/llm-obs/commit/a35b3f49b54cbfd548569c70dc70d0b3d8cc9d97))

### Chores

- Trigger ci for release sync
  ([`269c817`](https://github.com/makel0ve/llm-obs/commit/269c817d542800b7be30592a01706543d54c8b4a))


## v0.42.4 (2026-07-17)

### Bug Fixes

- Cache historical pricing correctly
  ([`a4341e6`](https://github.com/makel0ve/llm-obs/commit/a4341e65e51d8777a567f668744663642145d227))

### Chores

- Trigger ci for release sync
  ([`ec6371f`](https://github.com/makel0ve/llm-obs/commit/ec6371f58da7e85512362de671a71e1e10e75db9))


## v0.42.3 (2026-07-17)

### Bug Fixes

- Rate limit auth endpoints
  ([`4832e78`](https://github.com/makel0ve/llm-obs/commit/4832e78dc13f97b6584b01791f71415fd5b1b3f3))

### Chores

- Trigger ci for release sync
  ([`a2208a1`](https://github.com/makel0ve/llm-obs/commit/a2208a1d116970359a2e0e532dffbf573d7e2eb8))


## v0.42.2 (2026-07-17)

### Bug Fixes

- Load current user for jwt auth
  ([`12769a4`](https://github.com/makel0ve/llm-obs/commit/12769a4dbec59b423806f458d0509c1f1729c218))

### Chores

- Trigger ci for release sync
  ([`9563002`](https://github.com/makel0ve/llm-obs/commit/95630021848c21c7e5845a231783432733f4fef7))


## v0.42.1 (2026-07-17)

### Bug Fixes

- Reconcile retention cleanup
  ([`18e17de`](https://github.com/makel0ve/llm-obs/commit/18e17de968a76d5304d750b921f416aaeb6e4317))

### Chores

- Trigger ci for release sync
  ([`15156ed`](https://github.com/makel0ve/llm-obs/commit/15156edccde4c91c66090dad8a7a79f16b2a8ec4))


## v0.42.0 (2026-07-17)

### Chores

- Trigger ci for release sync
  ([`9ae7203`](https://github.com/makel0ve/llm-obs/commit/9ae72031fae32631d339338f19e94065a7a986c3))

### Features

- Expose payload storage status
  ([`68b3dc9`](https://github.com/makel0ve/llm-obs/commit/68b3dc919b4d23997bcceb10e84d9a18013f28be))


## v0.41.5 (2026-07-17)

### Bug Fixes

- Validate alert targets
  ([`759c8cd`](https://github.com/makel0ve/llm-obs/commit/759c8cd1a7ec4142b6d55d5ce3afafc22a70f9e6))

### Chores

- Trigger ci for release sync
  ([`7c3dd29`](https://github.com/makel0ve/llm-obs/commit/7c3dd29a944e3c98e6b8693bcc26664369ce0d8c))

### Testing

- Keep alert access payload valid
  ([`f5fcd39`](https://github.com/makel0ve/llm-obs/commit/f5fcd39f022977b9ab432a4fe667df8585765f7c))


## v0.41.4 (2026-07-16)

### Bug Fixes

- Update alert cooldown after delivery
  ([`50e61c8`](https://github.com/makel0ve/llm-obs/commit/50e61c8a41ee4b41d7592f64e4c8d6e762954b07))

### Chores

- Trigger ci for release sync
  ([`7b5b54f`](https://github.com/makel0ve/llm-obs/commit/7b5b54f4eced625aa8c37ddbd93044d3bbf5a6a1))


## v0.41.3 (2026-07-16)

### Bug Fixes

- Align alert rule semantics
  ([`721cddb`](https://github.com/makel0ve/llm-obs/commit/721cddb6a77a6559d65d03e99c36f32f0947aa75))

### Chores

- Trigger ci for release sync
  ([`4bc07d1`](https://github.com/makel0ve/llm-obs/commit/4bc07d10d5240d13c60f916a89af705715b41bc2))


## v0.41.2 (2026-07-16)

### Bug Fixes

- Stabilize trace identity
  ([`18f8f84`](https://github.com/makel0ve/llm-obs/commit/18f8f84a80e6cc11d25669c9241e0a3c66c015f1))

### Chores

- Trigger ci for release sync
  ([`5119811`](https://github.com/makel0ve/llm-obs/commit/51198116f82e8457efc83fff3550094d34b03c00))


## v0.41.1 (2026-07-16)

### Bug Fixes

- Calculate trace end time accurately
  ([`e722ebd`](https://github.com/makel0ve/llm-obs/commit/e722ebd3a8d8ae90a600e9ac35464fcbb7fd4aa4))

### Chores

- Trigger ci for release sync
  ([`2b89f44`](https://github.com/makel0ve/llm-obs/commit/2b89f44e76aa5e1145a6072301108b24dc8ea6a1))

### Testing

- Close parent span hierarchy audit
  ([`547ca79`](https://github.com/makel0ve/llm-obs/commit/547ca7947d1ab178dfbcb6ea6a067ba3433c0bbc))


## v0.41.0 (2026-07-16)

### Chores

- Trigger ci for release sync
  ([`fb19985`](https://github.com/makel0ve/llm-obs/commit/fb1998569b2b0ec29e51e93afb6e480b4f31077f))

### Features

- Report sdk span drops
  ([`9c1fb03`](https://github.com/makel0ve/llm-obs/commit/9c1fb03e4c67ff56ac11b2b3d3a3c87eb6fc5426))


## v0.40.4 (2026-07-16)

### Bug Fixes

- Harden trace pagination cursors
  ([`cabd77e`](https://github.com/makel0ve/llm-obs/commit/cabd77e3df80569fe12dbc948d36897f72cb8972))

### Chores

- Trigger ci for release sync
  ([`a1628fe`](https://github.com/makel0ve/llm-obs/commit/a1628fe0cdfbccaf987f9d918a38a1252fe26e0a))


## v0.40.3 (2026-07-16)

### Bug Fixes

- Support native otlp ids
  ([`1bf429a`](https://github.com/makel0ve/llm-obs/commit/1bf429af3b76155477edd2979e75e7538871b31a))

### Chores

- Trigger ci for release sync
  ([`4e32287`](https://github.com/makel0ve/llm-obs/commit/4e32287164c6be03a993a769f1c8886bd33ece9d))


## v0.40.2 (2026-07-16)

### Bug Fixes

- Enforce runtime database isolation
  ([`47f415b`](https://github.com/makel0ve/llm-obs/commit/47f415b0a1c3a97ac2840ff53b883d73eb268447))

- Enforce runtime database isolation
  ([`e1709c5`](https://github.com/makel0ve/llm-obs/commit/e1709c5209c3e8326bb2feb6827cdcc706085113))

### Chores

- Trigger ci for release sync
  ([`fe038c7`](https://github.com/makel0ve/llm-obs/commit/fe038c7ebf25ad40e7b3216d5b439bc4f62c69dc))


## v0.40.1 (2026-07-16)

### Bug Fixes

- Harden ingest queue durability
  ([`7333342`](https://github.com/makel0ve/llm-obs/commit/7333342ed3a6fcdd68f7e3074cc79b26406c6be2))

### Chores

- Trigger ci for release sync
  ([`1bdae40`](https://github.com/makel0ve/llm-obs/commit/1bdae401523e744260ec93c56ef6a1061bd2bcfb))


## v0.40.0 (2026-07-16)

### Chores

- Trigger ci for release sync
  ([`ae17c13`](https://github.com/makel0ve/llm-obs/commit/ae17c134e1e8da723c9c861504a22716b278e736))

### Features

- Edit user project access
  ([`cf5b376`](https://github.com/makel0ve/llm-obs/commit/cf5b3764247a4bcb0ca05c6080fb4cdf014a6aa8))


## v0.39.0 (2026-07-16)

### Chores

- Trigger ci for release sync
  ([`f2ddc94`](https://github.com/makel0ve/llm-obs/commit/f2ddc9487f584cd7352d07f9c8c421f42293a941))

### Features

- Assign projects during user creation
  ([`e2441ca`](https://github.com/makel0ve/llm-obs/commit/e2441caec9bd7770ad3d27cde7580f0b939aeae6))


## v0.38.0 (2026-07-15)

### Chores

- Trigger ci for release sync
  ([`d23480d`](https://github.com/makel0ve/llm-obs/commit/d23480da676ef50a8e4c9271db734ec7f3eb9d8d))

### Features

- Add organization admin settings
  ([`f793216`](https://github.com/makel0ve/llm-obs/commit/f793216cd5ac3a701d8268617706321b0ef34bc3))


## v0.37.0 (2026-07-15)

### Chores

- Trigger ci for release sync
  ([`d5f12f0`](https://github.com/makel0ve/llm-obs/commit/d5f12f02c5294dbe042f6f2af920fe4caa43f4e2))

### Features

- Make project switcher available to all users
  ([`06cbd19`](https://github.com/makel0ve/llm-obs/commit/06cbd196869e53e48b995adbb9a1e2768f981f5e))


## v0.36.0 (2026-07-15)

### Chores

- Trigger ci for release sync
  ([`41c3d58`](https://github.com/makel0ve/llm-obs/commit/41c3d581d4686205f04575ac7408b22d980704d7))

### Features

- Add project selection landing page
  ([`cc4cdae`](https://github.com/makel0ve/llm-obs/commit/cc4cdaecc77599abdb24ae1c32d2d6a6819a54cc))


## v0.35.0 (2026-07-15)

### Chores

- Trigger ci for release sync
  ([`a587bb1`](https://github.com/makel0ve/llm-obs/commit/a587bb155b96bda683c9164cd8508f7458e7b8a3))

### Documentation

- Harden production operations
  ([`b13d9cd`](https://github.com/makel0ve/llm-obs/commit/b13d9cd03411405377df1f1e3e1b142592ba1f74))

### Features

- Add error fingerprint analytics
  ([`2022b7c`](https://github.com/makel0ve/llm-obs/commit/2022b7c9c8f64f31b9b83f2d4b30eef9eb47f2d2))


## v0.34.1 (2026-07-14)

### Bug Fixes

- Make config test independent of environment
  ([`75bd2c9`](https://github.com/makel0ve/llm-obs/commit/75bd2c9c3fec27f6bad7e550895bb7dda955937d))

### Chores

- Trigger ci for release sync
  ([`faf358c`](https://github.com/makel0ve/llm-obs/commit/faf358c575fc72217affe87be02fab539a2e4014))

- Validate production environment
  ([`61f45bd`](https://github.com/makel0ve/llm-obs/commit/61f45bd69014666034529d067ea9cdfbb30b5fd7))


## v0.34.0 (2026-07-14)

### Chores

- Trigger ci for release sync
  ([`3bc4b2e`](https://github.com/makel0ve/llm-obs/commit/3bc4b2ee769e82e00d7a05766a54ed91263052e9))

### Features

- Add SDK diagnostics
  ([`bcb9c39`](https://github.com/makel0ve/llm-obs/commit/bcb9c3970cc30e29975b67162cabfc3c6f90b6c4))


## v0.33.0 (2026-07-14)

### Chores

- Trigger ci for release sync
  ([`17ca001`](https://github.com/makel0ve/llm-obs/commit/17ca001d97515211ab1c14511b3779798ec85130))

### Features

- Add SDK manual spans
  ([`a834d33`](https://github.com/makel0ve/llm-obs/commit/a834d33d74ecd9a6ecfbe0cad66b19f29368b65a))

### Testing

- Add frontend test tooling
  ([`ade1346`](https://github.com/makel0ve/llm-obs/commit/ade1346474b7991832699400d7a98aa39b9e0bf8))

- Cover dashboard flows
  ([`cb8d629`](https://github.com/makel0ve/llm-obs/commit/cb8d629f0ee1135a1410d54d1029f092854c9058))

- Cover frontend auth navigation
  ([`270cac1`](https://github.com/makel0ve/llm-obs/commit/270cac16a636df648041b8a2118334ae4efb847c))


## v0.32.0 (2026-07-14)

### Chores

- Trigger ci for release sync
  ([`a49f6c6`](https://github.com/makel0ve/llm-obs/commit/a49f6c6a496cf6376c7eddc17e4b65060d943478))

### Features

- Add worker health signal
  ([`e1597b6`](https://github.com/makel0ve/llm-obs/commit/e1597b6a17b7d5c7cc7e35c6202c804b26cfbf6a))


## v0.31.0 (2026-07-14)

### Chores

- Trigger ci for release sync
  ([`003d233`](https://github.com/makel0ve/llm-obs/commit/003d233fc8fe0b5745170b330efa8281644fad25))

### Features

- Add ingestion retry workflow
  ([`1314c41`](https://github.com/makel0ve/llm-obs/commit/1314c41260721532ba9de960aad35fa279419930))


## v0.30.0 (2026-07-14)

### Chores

- Trigger ci for release sync
  ([`ce530a4`](https://github.com/makel0ve/llm-obs/commit/ce530a45fc7b1d2214fdb299cc7174e7df8fb0fc))

### Features

- Show ingestion failure diagnostics
  ([`9a89226`](https://github.com/makel0ve/llm-obs/commit/9a8922695dd14f674a43af0e2551bf493ae28d69))


## v0.29.0 (2026-07-14)

### Chores

- Trigger ci for release sync
  ([`184a830`](https://github.com/makel0ve/llm-obs/commit/184a8305b1e281b615ceeb50e048884fb21035ef))

### Features

- Handle users without project access
  ([`e3aa2ca`](https://github.com/makel0ve/llm-obs/commit/e3aa2caf4f2c6f54e08c3aeac1ce59efabbdbef0))


## v0.28.0 (2026-07-14)

### Chores

- Trigger ci for release sync
  ([`0d6fc57`](https://github.com/makel0ve/llm-obs/commit/0d6fc57eb8346dc8a8cb07389e1130c2b760d514))

### Features

- Add project access management UI
  ([`0614b66`](https://github.com/makel0ve/llm-obs/commit/0614b6605e7dfadf3e84b74578bcc3d6ca383ac2))


## v0.27.0 (2026-07-14)

### Chores

- Trigger ci for release sync
  ([`c5d1af1`](https://github.com/makel0ve/llm-obs/commit/c5d1af17ad70968923c5310898772aa9e8b03f4a))

### Features

- Add project assignment api
  ([`b800708`](https://github.com/makel0ve/llm-obs/commit/b80070846f03f993c5a56c22ca2685f1982a0986))


## v0.26.0 (2026-07-13)

### Chores

- Trigger ci for release sync
  ([`5017c9e`](https://github.com/makel0ve/llm-obs/commit/5017c9ef614d8f9ff41c78b23ffa2835a3fba596))

### Features

- Enforce project access
  ([`3b5e7a7`](https://github.com/makel0ve/llm-obs/commit/3b5e7a766d3ef2f834a5a65f2ae63d565a37e053))


## v0.25.0 (2026-07-13)

### Chores

- Trigger ci for release sync
  ([`844b174`](https://github.com/makel0ve/llm-obs/commit/844b17431f417326a60788ae3c92a503cdf69e22))

### Features

- Add project membership schema
  ([`2ed7902`](https://github.com/makel0ve/llm-obs/commit/2ed79024cbb03176be2be15ceff10c10ab33749a))


## v0.24.0 (2026-07-13)

### Chores

- Trigger ci for release sync
  ([`bcda6ff`](https://github.com/makel0ve/llm-obs/commit/bcda6ff9d17ba825dce6fc505ac084600b2fb95b))

### Features

- Add project creation UI
  ([`73d9141`](https://github.com/makel0ve/llm-obs/commit/73d9141b56e3ea34c457a42c915b0e05e6525dd7))


## v0.23.0 (2026-07-13)

### Chores

- Trigger ci for release sync
  ([`a17abb0`](https://github.com/makel0ve/llm-obs/commit/a17abb07560189d59c4f019d01d9eebfb13679d6))

### Features

- Add admin project switcher
  ([`d434204`](https://github.com/makel0ve/llm-obs/commit/d43420484ee43f5df9fd796270f3c128a4ab23df))


## v0.22.0 (2026-07-13)

### Chores

- Trigger ci for release sync
  ([`1aa55c5`](https://github.com/makel0ve/llm-obs/commit/1aa55c57f9a7dd6049db62c614839bcc6556c77f))

### Features

- Add organization project API
  ([`3776d0e`](https://github.com/makel0ve/llm-obs/commit/3776d0ecb7f08cf8b2d0bbc20799bbeb2cc6d335))


## v0.21.0 (2026-07-13)

### Chores

- Trigger ci for release sync
  ([`fb5645a`](https://github.com/makel0ve/llm-obs/commit/fb5645acdf2c563b0cf93960706870561837290c))

### Features

- Show trace span hierarchy
  ([`4d7af07`](https://github.com/makel0ve/llm-obs/commit/4d7af0740c7c09963d022ebbb348ed28394103ba))


## v0.20.0 (2026-07-13)

### Chores

- Trigger ci for release sync
  ([`e256174`](https://github.com/makel0ve/llm-obs/commit/e2561748cd5b82bcc639b74be455d3464da71577))

### Features

- Persist parent span ids
  ([`357b203`](https://github.com/makel0ve/llm-obs/commit/357b20395311bb36f763294dae83d4c947ebec47))


## v0.19.0 (2026-07-13)

### Chores

- Trigger ci for release sync
  ([`e4b3a5d`](https://github.com/makel0ve/llm-obs/commit/e4b3a5d1a27e24c2faef4c68128b20e04141bec8))

### Features

- Propagate SDK parent spans
  ([`3e9a3b0`](https://github.com/makel0ve/llm-obs/commit/3e9a3b0625bc3269378a9846e8586ceae6ee3243))


## v0.18.2 (2026-07-12)

### Bug Fixes

- Tighten project API scoping
  ([`b9022a5`](https://github.com/makel0ve/llm-obs/commit/b9022a5bd126fd553e079c24d83b0fcb064ab0d9))

### Chores

- Trigger ci for release sync
  ([`646037c`](https://github.com/makel0ve/llm-obs/commit/646037c910b040fb3c485119548e393c84c2a631))

### Testing

- Cover tenant isolation boundaries
  ([`f4fbe08`](https://github.com/makel0ve/llm-obs/commit/f4fbe08c77387698dd9a471f59b5edfba1caa5c5))


## v0.18.1 (2026-07-10)

### Bug Fixes

- Harden trace row level security
  ([`bc78c6e`](https://github.com/makel0ve/llm-obs/commit/bc78c6e4b6d9afbe1e3295b54d7d6778797bb19b))

### Chores

- Ignore second development plan
  ([`9deb215`](https://github.com/makel0ve/llm-obs/commit/9deb21556f372c847166180b2f5781dfa3c64c60))

- Trigger ci for release sync
  ([`926a201`](https://github.com/makel0ve/llm-obs/commit/926a201a651458c4dbacc1537a69b5cb9a443925))

### Documentation

- Document tenant isolation audit
  ([`ac1ee75`](https://github.com/makel0ve/llm-obs/commit/ac1ee754a155568f6605c1f42fb93d97ac82dc79))

- Refresh product documentation
  ([`bc80ada`](https://github.com/makel0ve/llm-obs/commit/bc80adac1ec970d009f17f769e4e626937a7c904))


## v0.18.0 (2026-07-10)

### Chores

- Trigger ci for release sync
  ([`4f57e41`](https://github.com/makel0ve/llm-obs/commit/4f57e41c70b51716e0c7c2d585ce022925c36115))

### Features

- Add audit log UI
  ([`7f2c36d`](https://github.com/makel0ve/llm-obs/commit/7f2c36d85a05853c30b60dc8f154a915c83cc4f5))


## v0.17.0 (2026-07-09)

### Bug Fixes

- Avoid dynamic SQL in project settings update
  ([`6b2ff05`](https://github.com/makel0ve/llm-obs/commit/6b2ff056c0c71de44598d89b10c452b30a75b8f7))

### Chores

- Trigger ci for release sync
  ([`6bb0155`](https://github.com/makel0ve/llm-obs/commit/6bb015536e780a7e55d881cc76f8f5a67e1421a2))

### Features

- Add payload privacy controls
  ([`b971370`](https://github.com/makel0ve/llm-obs/commit/b9713705a9bc56901acc8cb745938f9b03b7f9cc))


## v0.16.0 (2026-07-09)

### Chores

- Trigger ci for release sync
  ([`0115af3`](https://github.com/makel0ve/llm-obs/commit/0115af31cabb7d59595efec63748e052331a9f8a))

### Features

- Add API key policies
  ([`d337dcd`](https://github.com/makel0ve/llm-obs/commit/d337dcd49701b5becd1c3fc2095dd0d57e8b321d))


## v0.15.0 (2026-07-09)

### Chores

- Trigger ci for release sync
  ([`1f9f669`](https://github.com/makel0ve/llm-obs/commit/1f9f669794e4de011c56bbb6b04e1f4afe9914a9))

### Documentation

- Add backup and restore guide
  ([`b029865`](https://github.com/makel0ve/llm-obs/commit/b029865e4451cda446f32f0630a205950d00bbaa))

- Add production runbooks
  ([`ddf6f3c`](https://github.com/makel0ve/llm-obs/commit/ddf6f3c76985fd0a50d531f1680e38f56c0943f2))

### Features

- Add organization user roles
  ([`763f201`](https://github.com/makel0ve/llm-obs/commit/763f201e671ac23a0a39f75fbbdf95f9a037f16e))


## v0.14.0 (2026-07-09)

### Chores

- Trigger ci for release sync
  ([`50861c3`](https://github.com/makel0ve/llm-obs/commit/50861c302a82f61f50c4763e9ed7251ca2002a01))

### Features

- Add error analytics
  ([`5f8abf5`](https://github.com/makel0ve/llm-obs/commit/5f8abf51a6f3705e0f16641123c978c2c04bab39))


## v0.13.0 (2026-07-08)

### Chores

- Trigger ci for release sync
  ([`54501f2`](https://github.com/makel0ve/llm-obs/commit/54501f29f80f5f6c56895c09703561a31a1449ea))

### Features

- Add cost and latency analytics
  ([`f77c4f7`](https://github.com/makel0ve/llm-obs/commit/f77c4f7a6d73de9f3a801bcc9ee65057ba3d8d08))


## v0.12.0 (2026-07-08)

### Chores

- Trigger ci for release sync
  ([`16c9027`](https://github.com/makel0ve/llm-obs/commit/16c9027b96db1f9e2d4977499b0736e1af292f69))

### Features

- Add pricing management UI
  ([`3311c84`](https://github.com/makel0ve/llm-obs/commit/3311c84552eabf2bd06c0a81dae5f5a3537c2c59))


## v0.11.0 (2026-07-08)

### Chores

- Trigger ci for release sync
  ([`e97cd03`](https://github.com/makel0ve/llm-obs/commit/e97cd039e64c8c86fbe2b30cb049d6979ee2add0))

### Features

- Add ingestion pipeline metrics
  ([`cff9cf6`](https://github.com/makel0ve/llm-obs/commit/cff9cf6a09f65de40a28ae8cc285b906e5c7209c))


## v0.10.0 (2026-07-08)

### Bug Fixes

- Handle failed task listing without project filter
  ([`77a7808`](https://github.com/makel0ve/llm-obs/commit/77a7808024080d0b5683780e70565dd522077084))

### Chores

- Trigger ci for release sync
  ([`e60de0e`](https://github.com/makel0ve/llm-obs/commit/e60de0e031fd2038b0bf8cf2337608b3b6a4d3ea))

### Features

- Expose failed ingestion tasks
  ([`ce81bfb`](https://github.com/makel0ve/llm-obs/commit/ce81bfbcc5ebb2126055da6bb66c0a3143a6eee6))


## v0.9.0 (2026-07-08)

### Chores

- Trigger ci for release sync
  ([`21610f3`](https://github.com/makel0ve/llm-obs/commit/21610f373223157632512d7df59c59c9ecf999c4))

### Features

- Add ingest batch status
  ([`e11cc15`](https://github.com/makel0ve/llm-obs/commit/e11cc15011089fbed049d28d84249ebfd7525a62))

### Testing

- Stabilize provider integrations
  ([`e5d0d01`](https://github.com/makel0ve/llm-obs/commit/e5d0d01ab9665d586f079cc4c8dc3278b670990d))


## v0.8.1 (2026-07-08)

### Bug Fixes

- Harden SDK shutdown behavior
  ([`555a402`](https://github.com/makel0ve/llm-obs/commit/555a402afa979cba954798900514f164990a8e38))

### Chores

- Trigger ci for release sync
  ([`8a70755`](https://github.com/makel0ve/llm-obs/commit/8a7075542ca8157d5affcdade0cbb982a285a670))

### Documentation

- Add SDK examples and troubleshooting
  ([`2aeab19`](https://github.com/makel0ve/llm-obs/commit/2aeab19262cb1306213ef0dc9b2d3051cd7f8d0a))

### Testing

- Stabilize dashboard frontend
  ([`9c47445`](https://github.com/makel0ve/llm-obs/commit/9c4744563b40ef72f3de88ec039998ad030e1848))


## v0.8.0 (2026-07-07)

### Chores

- Trigger ci for release sync
  ([`124142a`](https://github.com/makel0ve/llm-obs/commit/124142abe11c6895e0fae1889952c9ddfef6ea53))

### Features

- Add onboarding empty states
  ([`c195d11`](https://github.com/makel0ve/llm-obs/commit/c195d119158ee20affe9f452f8c8eb3e9fa7538c))


## v0.7.0 (2026-07-07)

### Chores

- Trigger ci for release sync
  ([`b2efbe2`](https://github.com/makel0ve/llm-obs/commit/b2efbe2923acf020196c4c2cc49eb57f0c208b85))

### Features

- Add alerts management UI
  ([`f7cefde`](https://github.com/makel0ve/llm-obs/commit/f7cefde04008c2efb39412f5dc43f7514d6dc8ef))


## v0.6.0 (2026-07-07)

### Chores

- Trigger ci for release sync
  ([`f892f82`](https://github.com/makel0ve/llm-obs/commit/f892f828b6fb9e3a5457afa786992b73e66f8f5a))

### Features

- Add project settings page
  ([`654df4c`](https://github.com/makel0ve/llm-obs/commit/654df4c43dbf910c5a2514483abc0131c7d95866))


## v0.5.1 (2026-07-07)

### Bug Fixes

- Clarify missing trace payload state
  ([`e421d54`](https://github.com/makel0ve/llm-obs/commit/e421d54ba561472b3275f551eb6767c613058b51))

### Chores

- Trigger ci for release sync
  ([`9968818`](https://github.com/makel0ve/llm-obs/commit/9968818ddf6e8b0d11c8d7714a1c24303d141de5))


## v0.5.0 (2026-07-07)

### Chores

- Trigger ci for release sync
  ([`b49c53b`](https://github.com/makel0ve/llm-obs/commit/b49c53b98215568bc21aa7de7e362988ce62bf4c))

### Features

- Add trace detail page
  ([`3489907`](https://github.com/makel0ve/llm-obs/commit/3489907fc7e7d777bdad57abd1849a377dd9ab14))


## v0.4.0 (2026-07-07)

### Chores

- Trigger ci for release sync
  ([`7ce64f8`](https://github.com/makel0ve/llm-obs/commit/7ce64f8c916b5a4db97aad5d267d471bbb3807f4))

### Features

- Add trace explorer page
  ([`a8288f4`](https://github.com/makel0ve/llm-obs/commit/a8288f4edf4d9cf1bae5535ebf82be10a588985f))


## v0.3.0 (2026-07-07)

### Chores

- Trigger ci for release sync
  ([`6fd261c`](https://github.com/makel0ve/llm-obs/commit/6fd261cc26def27bd6fa2080c659221689141b5e))

### Features

- Add dashboard navigation shell
  ([`891dcd4`](https://github.com/makel0ve/llm-obs/commit/891dcd43817dda06f75fbb6c73cc0c3ba0f17103))


## v0.2.3 (2026-07-05)

### Bug Fixes

- Add default trace span partitions
  ([`8592e5d`](https://github.com/makel0ve/llm-obs/commit/8592e5dec02125b269363a4d74226f50f52e992a))

### Chores

- Trigger ci for release sync
  ([`471d960`](https://github.com/makel0ve/llm-obs/commit/471d96015f2a3e7fc47ccc6e104bd2503f0eb0a2))

### Documentation

- Change gitignore
  ([`cde0285`](https://github.com/makel0ve/llm-obs/commit/cde0285d7dbaa902f1777284236d52c5c3e345d5))

- Clarify registration API key handling
  ([`441ab09`](https://github.com/makel0ve/llm-obs/commit/441ab09fbc618cf8e21d00599311c5aaca79c669))

### Testing

- Cover duplicate registration conflict
  ([`a258c75`](https://github.com/makel0ve/llm-obs/commit/a258c75fdbd92b0523993c971b6a3cd893e75ad3))

- Cover registration response contract
  ([`e276145`](https://github.com/makel0ve/llm-obs/commit/e2761456ba4191496278ebc1966adbeaedbcba25))


## v0.2.2 (2026-06-18)

### Bug Fixes

- Resolve frontend span stream lint errors
  ([`7c402a2`](https://github.com/makel0ve/llm-obs/commit/7c402a28c34adcfa6988240c0ae5bc1d87d764ff))

### Chores

- Trigger ci for release sync
  ([`277928d`](https://github.com/makel0ve/llm-obs/commit/277928dede222eec505dc74c0037e9de008616b7))


## v0.2.1 (2026-06-18)

### Bug Fixes

- Validate ingest span identifiers
  ([`9b43d8c`](https://github.com/makel0ve/llm-obs/commit/9b43d8c3400cc0440bf043bb24e2144a38393e0e))

### Chores

- Trigger ci for release sync
  ([`d4d2d2a`](https://github.com/makel0ve/llm-obs/commit/d4d2d2a4c5b4454fe1647a99e825e05d2b2030cf))


## v0.2.0 (2026-06-18)

### Chores

- Trigger ci for release sync
  ([`b1bc08a`](https://github.com/makel0ve/llm-obs/commit/b1bc08ad973b632e5e74c8774eaae9dc94da68fb))

### Documentation

- Document sdk shutdown
  ([`38311d7`](https://github.com/makel0ve/llm-obs/commit/38311d71fef0324710fa28f18fa51549c28e7111))

- Sync contributing checks with ci
  ([`cc6e0a0`](https://github.com/makel0ve/llm-obs/commit/cc6e0a03bb455f7f0ca01daac247e8f11e603f8d))

- Update readme ci and mvp scope
  ([`4a7b59d`](https://github.com/makel0ve/llm-obs/commit/4a7b59db631a15b49e78f031d59ed5509bfcdf89))

### Features

- Add registration flow to dashboard
  ([`f326069`](https://github.com/makel0ve/llm-obs/commit/f32606927d6f8355c112920fb9faaa3b41968c6f))

### Testing

- Cover sdk shutdown reinitialization
  ([`e59ecda`](https://github.com/makel0ve/llm-obs/commit/e59ecdae00411d1456003e659729a44fef4c1fd3))


## v0.1.2 (2026-06-18)

### Bug Fixes

- Cleanly shutdown sdk tracer task
  ([`8d19940`](https://github.com/makel0ve/llm-obs/commit/8d19940f848dca8e0797b127c6522ca1d8d8f99a))

### Chores

- Trigger ci for release sync
  ([`3bb2eea`](https://github.com/makel0ve/llm-obs/commit/3bb2eea7151daae655494633eb480a942acd507d))

- Trigger ci for release sync
  ([`7b477b4`](https://github.com/makel0ve/llm-obs/commit/7b477b4d5450bd6556717bef3f40f4f031e6b9ff))


## v0.1.1 (2026-06-17)

### Chores

- Merge main into develop sync branch
  ([`75e458f`](https://github.com/makel0ve/llm-obs/commit/75e458fa7fd0cb3d1b3ca3e523b6163226406543))


## v0.1.0 (2026-06-16)

### Bug Fixes

- Fixed ci
  ([`0fd20c4`](https://github.com/makel0ve/llm-obs/commit/0fd20c46010a0938c4b7cebaa229674e9e9b46e1))

- Fixed ci
  ([`8a878b0`](https://github.com/makel0ve/llm-obs/commit/8a878b087a3f9f5c882631c325c573184e053532))

- Fixed ci
  ([`51b8fdc`](https://github.com/makel0ve/llm-obs/commit/51b8fdc58082abbbd1ba92959f08bb16b5a150b4))

- Fixed ci
  ([`4b02ff0`](https://github.com/makel0ve/llm-obs/commit/4b02ff0b4b844aef19477cc0c5e02c9c67d713e9))

- Fixed ci
  ([`c80ed93`](https://github.com/makel0ve/llm-obs/commit/c80ed932f4716026d886a0d8f4869cc293ed7e3c))

- Fixed ci
  ([`84a91fa`](https://github.com/makel0ve/llm-obs/commit/84a91fa87f47ea158555035ca58264453f2245d7))

- Fixed ci
  ([`a26b85f`](https://github.com/makel0ve/llm-obs/commit/a26b85f92651ef10fe0e640c1c20d74b490bb630))

- Fixed ci
  ([`6398025`](https://github.com/makel0ve/llm-obs/commit/63980255f650170161fa5e3782423a427169f5cd))

- Force ssh for release pushes
  ([`8cdab7c`](https://github.com/makel0ve/llm-obs/commit/8cdab7c30824a5864bbf0b5ec2d16bfc92bfa2f7))

- Load release deploy key explicitly
  ([`fa462fa`](https://github.com/makel0ve/llm-obs/commit/fa462fa6de315a2996da2b1eae5907c4ddf0082c))

- Push releases through deploy key
  ([`650e678`](https://github.com/makel0ve/llm-obs/commit/650e6782af884cbc3f9fecb597bb89793f571c7e))

- Restore pytest compatibility for db sessions
  ([`37662ec`](https://github.com/makel0ve/llm-obs/commit/37662ec3b6e5847eba609a99fd0f19104c968378))

- Skip package build during release
  ([`3621a85`](https://github.com/makel0ve/llm-obs/commit/3621a852a735d3775ca112ba7aa48b31a2602fa3))

- Stabilize sdk initialization and realtime ingestion
  ([`bf378be`](https://github.com/makel0ve/llm-obs/commit/bf378bedc154564e82f71ef2d6ca08c6f696a9c8))

- Use deploy key for release commits
  ([`2a5dfc4`](https://github.com/makel0ve/llm-obs/commit/2a5dfc4183b64e01d82d415117b9cf3b3ce8f961))

- Use ssh remote for semantic release
  ([`9bf1d40`](https://github.com/makel0ve/llm-obs/commit/9bf1d402664b915a9e616a4e1070c3c3ad09b997))

### Chores

- Protect develop branch from direct commits
  ([`b34ec88`](https://github.com/makel0ve/llm-obs/commit/b34ec888c0bb47905febcd08867e4ee4e55eeace))

### Documentation

- Align readme with v1 project state
  ([`61df3bd`](https://github.com/makel0ve/llm-obs/commit/61df3bdfd01d6cb49a2746c7092f4204fe1598b2))

- Fixed readme
  ([`02dae1e`](https://github.com/makel0ve/llm-obs/commit/02dae1e53cef68b0a674a8035b3e5d56c54e7a80))

### Features

- Initial release v0.1.0
  ([`84dce70`](https://github.com/makel0ve/llm-obs/commit/84dce70b9a2b69d5118cdaa1408ca4c9a02b3e07))

### Testing

- Ci pipeline publishing flow
  ([`db4e89d`](https://github.com/makel0ve/llm-obs/commit/db4e89d4c35fd3c5b5aae03ef27ac71084328bb3))
