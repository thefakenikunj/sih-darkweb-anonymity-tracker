"""
Synthetic data collector for demonstration and evaluation.
Generates realistic darknet marketplace / forum persona data, observations, links, and ground truth.
"""

from typing import Dict, List, Tuple


def generate_synthetic_dataset() -> Tuple[List[Dict], List[Dict], List[Dict], Dict]:
    """
    Generates a realistic 12-entity dataset with 21 observations, 10 links, and ground truth data.
    
    Returns:
        Tuple containing:
        - entities (List[Dict])
        - observations (List[Dict])
        - links (List[Dict])
        - ground_truth (Dict)
    """

    entities = [
        {
            "entity_id": "cipher_king",
            "display_name": "CipherKing_Official",
            "entity_type": "persona",
            "source_platforms": ["Dread /v/DarknetMarkets"],
            "first_seen": "2026-01-01T10:15:00",
            "last_seen": "2026-03-02T18:45:00"
        },
        {
            "entity_id": "ck_logistics",
            "display_name": "CK_Logistics_EU",
            "entity_type": "persona",
            "source_platforms": ["Abacus Market"],
            "first_seen": "2026-03-07T12:00:00",
            "last_seen": "2026-05-21T09:30:00"
        },
        {
            "entity_id": "ghost_broker",
            "display_name": "GhostBroker_De",
            "entity_type": "persona",
            "source_platforms": ["Archetyp Market"],
            "first_seen": "2026-01-05T14:20:00",
            "last_seen": "2026-07-20T16:10:00"
        },
        {
            "entity_id": "dave_the_buyer",
            "display_name": "Dave_The_Buyer99",
            "entity_type": "persona",
            "source_platforms": ["Dread /v/DarknetMarkets"],
            "first_seen": "2026-01-11T08:00:00",
            "last_seen": "2026-01-11T11:20:00"
        },
        {
            "entity_id": "shadow_vending",
            "display_name": "ShadowVending",
            "entity_type": "persona",
            "source_platforms": ["Breached Forums"],
            "first_seen": "2026-01-21T11:00:00",
            "last_seen": "2026-04-11T14:15:00"
        },
        {
            "entity_id": "nightshade_vendor",
            "display_name": "Nightshade_Corp",
            "entity_type": "persona",
            "source_platforms": ["XSS Forum"],
            "first_seen": "2026-01-31T15:30:00",
            "last_seen": "2026-04-21T22:00:00"
        },
        {
            "entity_id": "lurker_909",
            "display_name": "lurker_909",
            "entity_type": "persona",
            "source_platforms": ["Exploit.in"],
            "first_seen": "2026-02-25T03:12:00",
            "last_seen": "2026-02-25T03:12:00"
        },
        {
            "entity_id": "nordic_pharma",
            "display_name": "NordicPharma_EU",
            "entity_type": "persona",
            "source_platforms": ["CryptBB"],
            "first_seen": "2026-01-06T09:00:00",
            "last_seen": "2026-05-01T17:40:00"
        },
        {
            "entity_id": "silk_route_dev",
            "display_name": "SilkRoute_Dev",
            "entity_type": "persona",
            "source_platforms": ["Github", "Dread"],
            "first_seen": "2026-02-01T10:00:00",
            "last_seen": "2026-06-12T19:00:00"
        },
        {
            "entity_id": "anon_coder404",
            "display_name": "AnonCoder404",
            "entity_type": "persona",
            "source_platforms": ["XSS Forum"],
            "first_seen": "2026-03-10T14:00:00",
            "last_seen": "2026-06-15T11:00:00"
        },
        {
            "entity_id": "hydra_reseller",
            "display_name": "Hydra_Reseller_01",
            "entity_type": "persona",
            "source_platforms": ["Telegram Channel"],
            "first_seen": "2026-04-05T08:00:00",
            "last_seen": "2026-07-01T13:20:00"
        },
        {
            "entity_id": "vortex_labs",
            "display_name": "VortexLabs",
            "entity_type": "persona",
            "source_platforms": ["Abacus Market"],
            "first_seen": "2026-05-10T11:30:00",
            "last_seen": "2026-08-01T16:00:00"
        }
    ]

    observations = [
        {
            "observation_id": "obs_101",
            "entity_id": "cipher_king",
            "platform": "Dread /v/DarknetMarkets",
            "content": "Official restock notice for Northern Europe. Verify PGP key before ordering: -----BEGIN PGP PUBLIC KEY BLOCK----- Fingerprint: 4F8B 92E1 3A21 C490 ... Contact via Jabber: cipherking@xmpp.is. FE disabled, Multisig Escrow only.",
            "observed_at": "2026-01-01T10:15:00",
            "tags": ["pgp_key", "jabber_id", "listing"]
        },
        {
            "observation_id": "obs_102",
            "entity_id": "cipher_king",
            "platform": "Dread /v/DarknetMarkets",
            "content": "WARNING: Do not deal with impersonators on Telegram. I only operate via PGP encrypted messages on Dread or Abacus.",
            "observed_at": "2026-01-15T14:22:00",
            "tags": ["warning", "policy"]
        },
        {
            "observation_id": "obs_150",
            "entity_id": "dave_the_buyer",
            "platform": "Dread /v/DarknetMarkets",
            "content": "Can anyone vouch for CipherKing_Official? Looking to place a bulk order for EU shipment, need reliable stealth.",
            "observed_at": "2026-01-11T08:00:00",
            "tags": ["vouch_request", "buyer"]
        },
        {
            "observation_id": "obs_204",
            "entity_id": "ck_logistics",
            "platform": "Abacus Market",
            "content": "New profile on Abacus due to domain migration. Same PGP Key Fingerprint: 4F8B 92E1 3A21 C490. All orders processed within 24h with vacuum sealed stealth.",
            "observed_at": "2026-03-07T12:00:00",
            "tags": ["pgp_key", "vendor_migration"]
        },
        {
            "observation_id": "obs_250",
            "entity_id": "ck_logistics",
            "platform": "Abacus Market",
            "content": "Stealth restocked. Multisig Escrow required for all buyers under 50 successful transactions. No direct deals allowed.",
            "observed_at": "2026-03-22T16:45:00",
            "tags": ["escrow_policy"]
        },
        {
            "observation_id": "obs_310",
            "entity_id": "ghost_broker",
            "platform": "Archetyp Market",
            "content": "Bulk batch price reduction for EU region. Escrow required as always. Send PGP encrypted shipping details to ghostbroker@xmpp.is.",
            "observed_at": "2026-04-01T09:10:00",
            "tags": ["stylometric_match", "pricing"]
        },
        {
            "observation_id": "obs_311",
            "entity_id": "ghost_broker",
            "platform": "Archetyp Market",
            "content": "BTC / XMR payments accepted. Direct Monero wallet deposit address available upon encrypted request.",
            "observed_at": "2026-04-10T11:05:00",
            "tags": ["crypto_payment"]
        },
        {
            "observation_id": "obs_401",
            "entity_id": "shadow_vending",
            "platform": "Breached Forums",
            "content": "Leaked database dump available. Verify identity using PGP fingerprint: D982 11AC 8071 FE32. Contact via Session ID: 05a2f89012...",
            "observed_at": "2026-01-21T11:00:00",
            "tags": ["pgp_key", "session_id"]
        },
        {
            "observation_id": "obs_402",
            "entity_id": "nightshade_vendor",
            "platform": "XSS Forum",
            "content": "Offering access logs and corporate databases. Same PGP key fingerprint: D982 11AC 8071 FE32. Standard escrow terms apply via forum middleman.",
            "observed_at": "2026-01-31T15:30:00",
            "tags": ["pgp_key", "forum_escrow"]
        },
        {
            "observation_id": "obs_403",
            "entity_id": "shadow_vending",
            "platform": "Breached Forums",
            "content": "yo just droppin a quick update, fresh db dump is up lol price lowered to $200 xmr hit my pm fast!!",
            "observed_at": "2026-02-15T20:12:00",
            "tags": ["informal_text", "stylometric_divergence"]
        },
        {
            "observation_id": "obs_404",
            "entity_id": "nightshade_vendor",
            "platform": "XSS Forum",
            "content": "Please be advised: the requested network infrastructure logs have been uploaded to our secure drop. Transactions are conducted strictly via PGP verification.",
            "observed_at": "2026-02-20T14:05:00",
            "tags": ["formal_text", "stylometric_divergence"]
        },
        {
            "observation_id": "obs_501",
            "entity_id": "lurker_909",
            "platform": "Exploit.in",
            "content": "+1 voucher for trusted escrow.",
            "observed_at": "2026-02-25T03:12:00",
            "tags": ["short_post"]
        },
        {
            "observation_id": "obs_601",
            "entity_id": "nordic_pharma",
            "platform": "CryptBB",
            "content": "Fresh pharmaceutical stock arriving Monday. Tracking numbers provided within 48h. Escrow mandatory.",
            "observed_at": "2026-01-06T09:00:00",
            "tags": ["vendor_listing"]
        },
        {
            "observation_id": "obs_602",
            "entity_id": "nordic_pharma",
            "platform": "CryptBB",
            "content": "Reminder: We do not accept Telegram orders. Escrow via CryptBB is non-negotiable for buyer security.",
            "observed_at": "2026-03-02T13:40:00",
            "tags": ["policy"]
        },
        {
            "observation_id": "obs_603",
            "entity_id": "nordic_pharma",
            "platform": "CryptBB",
            "content": "Price update for Q2 inventory. Monero address for direct orders: 888tX21... (escrow bypass requires prior vouch).",
            "observed_at": "2026-05-01T17:40:00",
            "tags": ["crypto_wallet"]
        },
        {
            "observation_id": "obs_701",
            "entity_id": "silk_route_dev",
            "platform": "Github",
            "content": "Published automated darknet escrow verification script written in Python. BTC wallet for donations: 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
            "observed_at": "2026-02-01T10:00:00",
            "tags": ["code_repository", "crypto_wallet"]
        },
        {
            "observation_id": "obs_702",
            "entity_id": "anon_coder404",
            "platform": "XSS Forum",
            "content": "Check my open source escrow tool on GitHub. If you find it useful, tip to my BTC address: 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
            "observed_at": "2026-03-10T14:00:00",
            "tags": ["crypto_wallet_match"]
        },
        {
            "observation_id": "obs_801",
            "entity_id": "hydra_reseller",
            "platform": "Telegram Channel",
            "content": "Fast delivery in CIS region. Contact @hydra_admin for price list.",
            "observed_at": "2026-04-05T08:00:00",
            "tags": ["telegram_contact"]
        },
        {
            "observation_id": "obs_802",
            "entity_id": "hydra_reseller",
            "platform": "Telegram Channel",
            "content": "Restock complete. Escrow accepted via Telegram Bot @hydra_escrow_bot.",
            "observed_at": "2026-07-01T13:20:00",
            "tags": ["telegram_bot"]
        },
        {
            "observation_id": "obs_901",
            "entity_id": "vortex_labs",
            "platform": "Abacus Market",
            "content": "VortexLabs opening sale! PGP Key: 77A1 B2C3 44D5 E6F7. High quality lab testing reports included.",
            "observed_at": "2026-05-10T11:30:00",
            "tags": ["pgp_key", "new_vendor"]
        },
        {
            "observation_id": "obs_902",
            "entity_id": "vortex_labs",
            "platform": "Abacus Market",
            "content": "All orders dispatched. Please leave feedback once received.",
            "observed_at": "2026-08-01T16:00:00",
            "tags": ["feedback_request"]
        }
    ]

    links = [
        {
            "source_id": "cipher_king",
            "target_id": "ck_logistics",
            "confidence_score": 0.98,
            "reason_codes": ["exact_pgp_match", "jabber_handle_match"],
            "method": "entity_resolution",
            "evidence_refs": ["obs_101", "obs_204"],
            "observed_at": "2026-03-07T12:00:00"
        },
        {
            "source_id": "ck_logistics",
            "target_id": "ghost_broker",
            "confidence_score": 0.65,
            "reason_codes": ["stylometric_similarity", "similar_phrasing_pattern"],
            "method": "stylometry",
            "evidence_refs": ["obs_250", "obs_310"],
            "observed_at": "2026-04-01T09:10:00"
        },
        {
            "source_id": "cipher_king",
            "target_id": "dave_the_buyer",
            "confidence_score": 0.22,
            "reason_codes": ["low_stylometric_similarity"],
            "method": "stylometry",
            "evidence_refs": ["obs_101", "obs_150"],
            "observed_at": "2026-01-11T08:00:00"
        },
        {
            "source_id": "shadow_vending",
            "target_id": "nightshade_vendor",
            "confidence_score": 0.92,
            "reason_codes": ["exact_pgp_match"],
            "method": "entity_resolution",
            "evidence_refs": ["obs_401", "obs_402"],
            "observed_at": "2026-01-31T15:30:00"
        },
        {
            "source_id": "shadow_vending",
            "target_id": "nightshade_vendor",
            "confidence_score": 0.28,
            "reason_codes": ["stylometric_dissimilarity"],
            "method": "stylometry",
            "evidence_refs": ["obs_403", "obs_404"],
            "observed_at": "2026-02-20T14:05:00"
        },
        {
            "source_id": "silk_route_dev",
            "target_id": "anon_coder404",
            "confidence_score": 0.96,
            "reason_codes": ["crypto_wallet_reuse"],
            "method": "entity_resolution",
            "evidence_refs": ["obs_701", "obs_702"],
            "observed_at": "2026-03-10T14:00:00"
        },
        {
            "source_id": "nordic_pharma",
            "target_id": "cipher_king",
            "confidence_score": 0.35,
            "reason_codes": ["common_escrow_phrasing"],
            "method": "stylometry",
            "evidence_refs": ["obs_101", "obs_602"],
            "observed_at": "2026-03-02T13:40:00"
        },
        {
            "source_id": "hydra_reseller",
            "target_id": "vortex_labs",
            "confidence_score": 0.15,
            "reason_codes": ["no_identifying_overlap"],
            "method": "entity_resolution",
            "evidence_refs": ["obs_801", "obs_901"],
            "observed_at": "2026-05-10T11:30:00"
        },
        {
            "source_id": "ghost_broker",
            "target_id": "cipher_king",
            "confidence_score": 0.61,
            "reason_codes": ["stylometric_similarity", "xmpp_domain_overlap"],
            "method": "stylometry",
            "evidence_refs": ["obs_101", "obs_310"],
            "observed_at": "2026-04-01T09:10:00"
        },
        {
            "source_id": "lurker_909",
            "target_id": "shadow_vending",
            "confidence_score": 0.10,
            "reason_codes": ["insufficient_data"],
            "method": "stylometry",
            "evidence_refs": ["obs_401", "obs_501"],
            "observed_at": "2026-02-25T03:12:00"
        }
    ]

    ground_truth = {
        "same_persona_clusters": [
            ["cipher_king", "ck_logistics", "ghost_broker"],
            ["shadow_vending", "nightshade_vendor"],
            ["silk_route_dev", "anon_coder404"]
        ],
        "known_non_matches": [
            ["cipher_king", "dave_the_buyer"],
            ["shadow_vending", "lurker_909"],
            ["hydra_reseller", "vortex_labs"]
        ],
        "unresolved": [
            "lurker_909"
        ],
        "no_claim": [
            "nordic_pharma",
            "vortex_labs"
        ]
    }

    return entities, observations, links, ground_truth
class SyntheticCollector:
    def collect(self):
        return generate_synthetic_dataset()