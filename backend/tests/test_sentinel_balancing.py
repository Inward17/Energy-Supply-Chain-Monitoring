from src.agents.sentinel_agent import _select_balanced_batch, _source_category


def _row(row_id: int, domain: str) -> dict:
    return {
        'id': row_id,
        'url': f'https://{domain}/energy/{row_id}',
        'title': f'Synthetic energy article {row_id}',
        'article_category': 'general',
    }


def test_source_category_matches_subdomains_and_local_outlets():
    assert _source_category('https://www.reuters.com/world/energy') == 'major_global'
    assert _source_category('https://markets.ft.com/data') == 'major_global'
    assert _source_category('https://www.spglobal.com/commodityinsights') == 'industrial'
    assert _source_category('https://middleeasteye.net/news/example') == 'local'
    assert _source_category('https://example.org/energy') == 'unclassified'


def test_balanced_batch_enforces_six_two_two_mix():
    rows = (
        [_row(i, 'reuters.com') for i in range(1, 11)]
        + [_row(i, 'oilprice.com') for i in range(11, 17)]
        + [_row(i, 'aljazeera.com') for i in range(17, 23)]
        + [_row(i, 'example.org') for i in range(23, 31)]
    )

    batch = _select_balanced_batch(rows, batch_size=10)
    categories = [_source_category(row['url']) for row in batch]

    assert len(batch) == 10
    assert categories.count('major_global') == 6
    assert categories.count('industrial') == 2
    assert categories.count('local') == 2


def test_balanced_batch_fills_category_shortfalls_to_capacity():
    rows = (
        [_row(1, 'reuters.com')]
        + [_row(i, 'lloydslist.com') for i in range(2, 6)]
        + [_row(6, 'arabnews.com')]
        + [_row(i, 'unclassified.example') for i in range(7, 15)]
    )

    batch = _select_balanced_batch(rows, batch_size=10)

    assert len(batch) == 10
    assert len({row['id'] for row in batch}) == 10
    assert any(_source_category(row['url']) == 'unclassified' for row in batch)


def test_balanced_batch_returns_every_row_when_pool_is_smaller_than_batch():
    rows = [_row(1, 'reuters.com'), _row(2, 'unknown.example')]

    assert len(_select_balanced_batch(rows, batch_size=10)) == 2


def test_domain_mix_preserves_producer_and_chokepoint_coverage():
    rows = (
        [
            {**_row(i, 'reuters.com'), 'article_category': 'chokepoint'}
            for i in range(1, 9)
        ]
        + [
            {**_row(i, 'oilprice.com'), 'article_category': 'chokepoint'}
            for i in range(9, 12)
        ]
        + [
            {**_row(i, 'aljazeera.com'), 'article_category': 'chokepoint'}
            for i in range(12, 15)
        ]
        + [
            {**_row(15, 'middleeasteye.net'), 'article_category': 'producer_nation'}
        ]
    )

    batch = _select_balanced_batch(rows, batch_size=10)
    source_categories = [_source_category(row['url']) for row in batch]
    article_categories = {row['article_category'] for row in batch}

    assert source_categories.count('major_global') == 6
    assert source_categories.count('industrial') == 2
    assert source_categories.count('local') == 2
    assert {'producer_nation', 'chokepoint'} <= article_categories
