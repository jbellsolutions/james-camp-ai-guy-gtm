# Sample affiliate program (fictional)

Northwind Outdoor Gear, Denver CO, and six affiliates: a hiking blog, a review site, a trail running newsletter, a
coupon site, a climbing community and a customer. Every name, number and address is invented: phones are 555-01xx
and every domain ends in example.com. Partner types come from `data/affiliate-partner-types.json`.

```bash
./orgo/relationship.sh import apply csv examples/relationship --client "Northwind Outdoor Gear"
```

That builds a card for every person, partner and partnership in the vault. `tests/test_relationship_cards.py`
imports this sample on every run.
