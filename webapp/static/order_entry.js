/**
 * Order Entry module.
 *
 * All client-side logic for the order entry page lives under the OE namespace
 * to avoid polluting the global scope and to keep handlers reusable.
 */
var OE = (function () {
    'use strict';

    // -- State ----------------------------------------------------------------

    var _orderId = (typeof ORDER_DATA !== 'undefined' && ORDER_DATA.id) ? ORDER_DATA.id : null;
    var _lines = (typeof ORDER_LINES !== 'undefined') ? ORDER_LINES : [];
    var _customers = [];
    var _allItems = [];
    var _shipMethods = [];
    var _addresses = [];
    var _selectedItem = null;
    var _searchTimer = null;
    var _scannerStream = null;
    var _entryMode = 'single';

    // -- Helpers --------------------------------------------------------------

    function _debounce(fn, ms) {
        var timer;
        return function () {
            var args = arguments, ctx = this;
            clearTimeout(timer);
            timer = setTimeout(function () { fn.apply(ctx, args); }, ms);
        };
    }

    function _formatCurrency(val) {
        var n = parseFloat(val) || 0;
        return '$' + n.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    }

    function _api(method, url, body) {
        var opts = { method: method, headers: { 'Content-Type': 'application/json' } };
        if (body !== undefined) opts.body = JSON.stringify(body);
        return fetch(url, opts).then(function (r) { return r.json(); });
    }

    function _showToast(msg, type) {
        var el = document.createElement('div');
        el.className = 'oe-toast oe-toast-' + (type || 'info');
        el.textContent = msg;
        document.body.appendChild(el);
        setTimeout(function () { el.classList.add('oe-toast-show'); }, 10);
        setTimeout(function () {
            el.classList.remove('oe-toast-show');
            setTimeout(function () { el.remove(); }, 300);
        }, 3000);
    }

    function _closeAllDropdowns() {
        document.querySelectorAll('.oe-dropdown').forEach(function (d) {
            d.style.display = 'none';
        });
    }

    // -- Tabs -----------------------------------------------------------------

    function switchTab(tab) {
        document.querySelectorAll('.oe-tab').forEach(function (t) {
            t.classList.toggle('active', t.getAttribute('data-tab') === tab);
        });
        document.querySelectorAll('.oe-tab-content').forEach(function (c) {
            c.classList.remove('active');
        });
        var target = tab === 'header' ? 'tabHeader' : 'tabLines';
        document.getElementById(target).classList.add('active');

        if (tab === 'lines') {
            _checkHeaderComplete();
        }
    }

    function _checkHeaderComplete() {
        var missing = [];
        if (!document.getElementById('customerAccount').value) missing.push('Customer');
        if (!document.getElementById('shipDate').value) missing.push('Ship date');
        if (!document.getElementById('shipMethod').value) missing.push('Ship method');
        if (!document.getElementById('poNumber').value) missing.push('PO number');
        if (!document.getElementById('addressSelect').value) missing.push('Address');

        var warn = document.getElementById('headerWarning');
        var badge = document.getElementById('headerBadge');
        if (missing.length > 0) {
            warn.style.display = 'flex';
            badge.textContent = '!';
            badge.style.display = 'inline-flex';
        } else {
            warn.style.display = 'none';
            badge.style.display = 'none';
        }
    }

    // -- Customer search ------------------------------------------------------

    function _loadCustomers() {
        _api('GET', '/api/customers').then(function (data) {
            _customers = Array.isArray(data) ? data : [];
        });
    }

    function _renderCustomerDropdown(matches) {
        var dd = document.getElementById('customerDropdown');
        if (!matches.length) { dd.style.display = 'none'; return; }
        dd.innerHTML = matches.map(function (c) {
            return '<div class="oe-dropdown-item" data-account="' + c.account + '" data-name="' + c.name + '">'
                 + '<span class="oe-dd-primary">' + c.name + '</span>'
                 + '<span class="oe-dd-secondary">' + c.account + '</span>'
                 + '</div>';
        }).join('');
        dd.style.display = 'block';
        dd.querySelectorAll('.oe-dropdown-item').forEach(function (item) {
            item.addEventListener('click', function () {
                _selectCustomer(this.getAttribute('data-account'), this.getAttribute('data-name'));
            });
        });
    }

    function searchCustomers(query) {
        if (!query) {
            _renderCustomerDropdown(_customers.slice(0, 30));
            return;
        }
        var q = query.toLowerCase();
        var matches = _customers.filter(function (c) {
            return c.name.toLowerCase().indexOf(q) !== -1 ||
                   c.account.toLowerCase().indexOf(q) !== -1;
        }).slice(0, 30);
        _renderCustomerDropdown(matches);
    }

    function showCustomerDropdown() {
        var query = document.getElementById('customerSearch').value.trim();
        searchCustomers(query);
    }

    function _selectCustomer(account, name) {
        document.getElementById('customerAccount').value = account;
        document.getElementById('customerSearch').value = '';
        document.getElementById('customerChip').style.display = 'flex';
        document.getElementById('customerChipText').textContent = name + ' (' + account + ')';
        document.getElementById('customerDropdown').style.display = 'none';
        document.getElementById('orderSubtitle').textContent = name;
        _loadAddresses(account);
        _loadItems();
    }

    function clearCustomer() {
        document.getElementById('customerAccount').value = '';
        document.getElementById('customerChip').style.display = 'none';
        document.getElementById('customerSearch').value = '';
        document.getElementById('orderSubtitle').textContent = 'Fill in order details';
        _addresses = [];
        clearAddress();
    }

    // -- Addresses ------------------------------------------------------------

    function _loadAddresses(account) {
        if (!account) return;
        _api('GET', '/api/customer-addresses/' + encodeURIComponent(account))
            .then(function (data) {
                _addresses = data.addresses || [];
            })
            .catch(function (err) {
                console.error('Failed to load addresses:', err);
                _addresses = [];
            });
    }

    function _filterAddresses(query) {
        var list = _addresses;
        if (query) {
            var q = query.toLowerCase();
            list = list.filter(function (a) {
                return (a.address_text || '').toLowerCase().indexOf(q) !== -1
                    || (a.label || '').toLowerCase().indexOf(q) !== -1
                    || (a.address_id || '').toLowerCase().indexOf(q) !== -1;
            });
        }
        return list.slice(0, 40);
    }

    function _renderAddressDropdown(matches) {
        var dd = document.getElementById('addressDropdown');
        var html = '<div class="oe-dropdown-item oe-dropdown-action" data-action="new">'
                 + '<span class="oe-dd-primary" style="color:var(--primary);">+ Add New Address</span>'
                 + '</div>';
        matches.forEach(function (a) {
            var prefix = a.address_id ? '[' + _escHtml(a.address_id) + '] ' : '';
            html += '<div class="oe-dropdown-item" data-addr-id="' + a.id + '">'
                  + '<span class="oe-dd-primary">' + prefix + _escHtml(a.label || '') + '</span>'
                  + '<span class="oe-dd-secondary">' + _escHtml(a.address_text) + '</span>'
                  + (a.is_default ? '<span class="oe-dd-desc" style="color:var(--primary);">Default</span>' : '')
                  + '</div>';
        });
        if (!matches.length) {
            html += '<div class="oe-dropdown-item" style="pointer-events:none;">'
                  + '<span class="oe-dd-secondary">No addresses found</span></div>';
        }
        dd.innerHTML = html;
        dd.style.display = 'block';
        dd.querySelectorAll('.oe-dropdown-item').forEach(function (el) {
            el.addEventListener('click', function () {
                if (this.getAttribute('data-action') === 'new') {
                    dd.style.display = 'none';
                    document.getElementById('newAddressForm').style.display = 'block';
                    return;
                }
                var addrDbId = parseInt(this.getAttribute('data-addr-id'));
                if (!addrDbId) return;
                var addr = _addresses.filter(function (a) { return a.id === addrDbId; })[0];
                if (addr) _selectAddress(addr);
            });
        });
    }

    function _selectAddress(addr) {
        document.getElementById('addressSelect').value = addr.id;
        document.getElementById('addressSearch').value = '';
        document.getElementById('addressDropdown').style.display = 'none';
        document.getElementById('addressChip').style.display = 'flex';
        var prefix = addr.address_id ? '[' + addr.address_id + '] ' : '';
        document.getElementById('addressChipText').textContent = prefix + (addr.label || addr.address_text);
        document.getElementById('newAddressForm').style.display = 'none';
    }

    function searchAddresses(query) {
        _renderAddressDropdown(_filterAddresses(query));
    }

    function showAddressDropdown() {
        var query = document.getElementById('addressSearch').value.trim();
        _renderAddressDropdown(_filterAddresses(query));
    }

    function clearAddress() {
        document.getElementById('addressSelect').value = '';
        document.getElementById('addressChip').style.display = 'none';
        document.getElementById('addressSearch').value = '';
    }

    function onAddressChange() {}

    function saveNewAddress() {
        var account = document.getElementById('customerAccount').value;
        if (!account) { _showToast('Select a customer first', 'error'); return; }
        var addrId = (document.getElementById('newAddrId').value || '').trim().toUpperCase().substring(0, 5);
        var label = document.getElementById('newAddressLabel').value.trim();
        var street = document.getElementById('newAddrStreet').value.trim();
        var city = document.getElementById('newAddrCity').value.trim();
        var state = document.getElementById('newAddrState').value.trim();
        var zip = document.getElementById('newAddrZip').value.trim();
        var country = document.getElementById('newAddrCountry').value.trim();

        if (!street) { _showToast('Type and select an address first', 'error'); return; }

        var parts = [street, city, state, zip, country].filter(Boolean);
        var addrText = parts.join(', ');

        _api('POST', '/api/customer-addresses/' + encodeURIComponent(account), {
            address_id: addrId, label: label, address_text: addrText,
            street: street, city: city, state: state,
            zip_code: zip, country: country,
        }).then(function (d) {
            if (d.success) {
                var newAddr = {
                    id: d.id, address_id: addrId,
                    label: label || addrText.substring(0, 60),
                    address_text: addrText, is_default: 0,
                };
                _addresses.push(newAddr);
                _selectAddress(newAddr);
                cancelNewAddress();
                _showToast('Address saved', 'success');
            }
        });
    }

    function cancelNewAddress() {
        document.getElementById('newAddressForm').style.display = 'none';
        document.getElementById('newAddrId').value = '';
        document.getElementById('newAddressLabel').value = '';
        document.getElementById('newAddrAutocomplete').value = '';
        document.getElementById('newAddrStreet').value = '';
        document.getElementById('newAddrCity').value = '';
        document.getElementById('newAddrState').value = '';
        document.getElementById('newAddrZip').value = '';
        document.getElementById('newAddrCountry').value = 'US';
        document.getElementById('newAddrParsed').style.display = 'none';
        document.getElementById('newAddrAutocomplete').style.display = '';
    }

    function clearParsedAddress() {
        document.getElementById('newAddrStreet').value = '';
        document.getElementById('newAddrCity').value = '';
        document.getElementById('newAddrState').value = '';
        document.getElementById('newAddrZip').value = '';
        document.getElementById('newAddrCountry').value = 'US';
        document.getElementById('newAddrParsed').style.display = 'none';
        var ac = document.getElementById('newAddrAutocomplete');
        ac.value = '';
        ac.style.display = '';
        ac.focus();
    }

    function _showParsedAddress() {
        var parts = [
            document.getElementById('newAddrStreet').value,
            document.getElementById('newAddrCity').value,
            document.getElementById('newAddrState').value,
            document.getElementById('newAddrZip').value,
        ].filter(Boolean);
        if (!parts.length) return;
        document.getElementById('newAddrParsedText').textContent = parts.join(', ');
        document.getElementById('newAddrParsed').style.display = 'flex';
        document.getElementById('newAddrAutocomplete').style.display = 'none';
    }

    function autoGenAddrId() {
        var existing = _addresses.map(function (a) { return (a.address_id || '').toUpperCase(); });
        var city = (document.getElementById('newAddrCity').value || '').trim().toUpperCase();
        var prefix = city ? city.substring(0, 3) : 'AD';
        for (var i = 1; i <= 99; i++) {
            var candidate = prefix + (i < 10 ? '0' + i : '' + i);
            candidate = candidate.substring(0, 5);
            if (existing.indexOf(candidate) === -1) {
                document.getElementById('newAddrId').value = candidate;
                return;
            }
        }
        document.getElementById('newAddrId').value = prefix + '99';
    }

    function autoGenAddrLabel() {
        var street = (document.getElementById('newAddrStreet').value || '').trim();
        var city = (document.getElementById('newAddrCity').value || '').trim();
        var label = street ? (street + (city ? ', ' + city : '')) : city;
        document.getElementById('newAddressLabel').value = label.substring(0, 60);
    }

    // -- Ship methods ---------------------------------------------------------

    function _loadShipMethods() {
        _api('GET', '/api/ship-methods').then(function (data) {
            _shipMethods = data.methods || [];
            var sel = document.getElementById('shipMethod');
            _shipMethods.forEach(function (m) {
                var opt = document.createElement('option');
                opt.value = m.code;
                opt.textContent = m.name;
                sel.appendChild(opt);
            });
            if (typeof ORDER_DATA !== 'undefined' && ORDER_DATA.ship_method) {
                sel.value = ORDER_DATA.ship_method;
            }
        });
    }

    // -- PO generation --------------------------------------------------------

    function generatePO() {
        var account = document.getElementById('customerAccount').value;
        if (!account) { _showToast('Select a customer first', 'error'); return; }
        _api('POST', '/api/orders/generate-po/' + encodeURIComponent(account))
            .then(function (d) {
                if (d.po_number) {
                    document.getElementById('poNumber').value = d.po_number;
                    _showToast('PO generated: ' + d.po_number, 'success');
                }
            });
    }

    // -- Item catalog ---------------------------------------------------------

    function _loadItems() {
        var customer = document.getElementById('customerAccount').value;
        var url = '/api/items?q=';
        if (customer) url += '&customer=' + encodeURIComponent(customer);
        _api('GET', url).then(function (data) {
            _allItems = data.items || [];
        });
    }

    function _filterItems(query) {
        if (!query) return _allItems.slice(0, 50);
        var q = query.toLowerCase();
        return _allItems.filter(function (it) {
            return it.item_number.toLowerCase().indexOf(q) !== -1
                || it.item_name.toLowerCase().indexOf(q) !== -1
                || (it.description && it.description.toLowerCase().indexOf(q) !== -1)
                || (it.upc && it.upc.indexOf(q) !== -1);
        }).slice(0, 50);
    }

    function _escHtml(s) {
        if (!s) return '';
        return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }

    function _renderItemDropdown(items, dropdownId, clickHandler) {
        var dd = document.getElementById(dropdownId);
        if (!items.length) { dd.style.display = 'none'; return; }
        dd.innerHTML = items.map(function (it) {
            var desc = it.description ? '<span class="oe-dd-desc">' + _escHtml(it.description) + '</span>' : '';
            return '<div class="oe-dropdown-item" data-item=\'' + JSON.stringify(it).replace(/'/g, '&#39;') + '\'>'
                 + '<span class="oe-dd-primary">' + _escHtml(it.item_number) + '</span>'
                 + '<span class="oe-dd-secondary">' + _escHtml(it.item_name)
                 + (it.group ? ' &middot; ' + _escHtml(it.group) : '') + '</span>'
                 + desc
                 + '</div>';
        }).join('');
        dd.style.display = 'block';
        dd.querySelectorAll('.oe-dropdown-item').forEach(function (el) {
            el.addEventListener('click', function () {
                clickHandler(JSON.parse(this.getAttribute('data-item')));
            });
        });
    }

    function searchItems(query) {
        var matches = _filterItems(query);
        _renderItemDropdown(matches, 'itemDropdown', function (item) {
            _selectItem(item);
        });
    }

    function showItemDropdown() {
        var query = document.getElementById('itemSearch').value.trim();
        searchItems(query);
    }

    function _selectItem(item) {
        _selectedItem = item;
        document.getElementById('selectedItemNumber').value = item.item_number;
        document.getElementById('selectedCasePack').value = item.case_pack || 1;
        document.getElementById('selectedBookPrice').value = item.book_price || 0;
        document.getElementById('itemSearch').value = '';
        document.getElementById('itemDropdown').style.display = 'none';
        document.getElementById('itemChip').style.display = 'flex';
        var chipLabel = item.item_number + (item.description ? ' — ' + item.description : (item.item_name ? ' — ' + item.item_name : ''));
        document.getElementById('itemChipText').textContent = chipLabel;

        var cp = item.case_pack || 1;
        var label = document.getElementById('casePackLabel');
        if (cp > 1) {
            label.textContent = 'Case of ' + cp;
            label.style.display = 'block';
        } else {
            label.style.display = 'none';
        }

        document.getElementById('lineQty').value = cp;
        document.getElementById('lineQty').step = cp;
        document.getElementById('lineQty').min = cp;

        document.getElementById('customerPriceDisplay').textContent = _formatCurrency(item.customer_price || 0);

        var bookTip = document.getElementById('bookPriceTip');
        var bookTooltip = document.getElementById('bookPriceTooltip');
        if (item.book_price) {
            bookTooltip.textContent = 'Book price: ' + _formatCurrency(item.book_price);
            bookTip.style.display = 'inline-flex';
        } else {
            bookTip.style.display = 'none';
        }

        document.getElementById('customPrice').value = '';
        document.getElementById('updateCustomerPrice').checked = false;
        recalcExtended();

        _fetchCustomerPrice(item.item_number);
    }

    function _fetchCustomerPrice(itemNumber) {
        var account = document.getElementById('customerAccount').value;
        if (!account || !itemNumber) return;

        _api('GET', '/api/customer-price/' + encodeURIComponent(account) + '/' + encodeURIComponent(itemNumber))
            .then(function (data) {
                if (!_selectedItem || _selectedItem.item_number !== itemNumber) return;

                var custPrice = data.customer_price || 0;
                var bookPrice = data.book_price || 0;

                _selectedItem.customer_price = custPrice;
                _selectedItem.book_price = bookPrice;
                document.getElementById('selectedBookPrice').value = bookPrice;
                document.getElementById('customerPriceDisplay').textContent = _formatCurrency(custPrice);

                var bookTip = document.getElementById('bookPriceTip');
                var bookTooltip = document.getElementById('bookPriceTooltip');
                if (bookPrice && bookPrice !== custPrice) {
                    bookTooltip.textContent = 'Book price: ' + _formatCurrency(bookPrice)
                        + (data.source === 'trade_agreement' ? ' (trade agreement applied)' : '');
                    bookTip.style.display = 'inline-flex';
                } else if (data.source === 'trade_agreement') {
                    bookTooltip.textContent = 'Trade agreement price';
                    bookTip.style.display = 'inline-flex';
                } else {
                    bookTip.style.display = 'none';
                }

                recalcExtended();
            })
            .catch(function () {});
    }

    function clearItem() {
        _selectedItem = null;
        document.getElementById('selectedItemNumber').value = '';
        document.getElementById('itemChip').style.display = 'none';
        document.getElementById('casePackLabel').style.display = 'none';
        document.getElementById('lineQty').value = 0;
        document.getElementById('lineQty').step = 1;
        document.getElementById('lineQty').min = 0;
        document.getElementById('customerPriceDisplay').textContent = '$0.00';
        document.getElementById('bookPriceTip').style.display = 'none';
        document.getElementById('customPrice').value = '';
        document.getElementById('extendedPrice').textContent = '$0.00';
    }

    // -- Quantity stepper -----------------------------------------------------

    function adjustQty(direction) {
        var input = document.getElementById('lineQty');
        var cp = parseInt(document.getElementById('selectedCasePack').value) || 1;
        var current = parseInt(input.value) || 0;
        var next = current + (direction * cp);
        if (next < 0) next = 0;
        input.value = next;
        recalcExtended();
    }

    function onQtyChange() {
        var input = document.getElementById('lineQty');
        var cp = parseInt(document.getElementById('selectedCasePack').value) || 1;
        var val = parseInt(input.value) || 0;
        if (cp > 1 && val % cp !== 0) {
            val = Math.round(val / cp) * cp;
            if (val < cp) val = cp;
            input.value = val;
        }
        recalcExtended();
    }

    function recalcExtended() {
        var qty = parseInt(document.getElementById('lineQty').value) || 0;
        var custom = parseFloat(document.getElementById('customPrice').value);
        var price = !isNaN(custom) && custom > 0 ? custom : (_selectedItem ? (_selectedItem.customer_price || 0) : 0);
        document.getElementById('extendedPrice').textContent = _formatCurrency(qty * price);
    }

    // -- Add / edit / remove lines --------------------------------------------

    function _ensureOrder() {
        if (_orderId) return Promise.resolve(_orderId);
        return _api('POST', '/api/orders', _gatherHeader()).then(function (d) {
            if (d.id) {
                _orderId = d.id;
                history.replaceState(null, '', '/orders/' + _orderId);
            }
            return _orderId;
        });
    }

    function _gatherHeader() {
        var addrSel = document.getElementById('addressSelect');
        var addrId = addrSel.value && addrSel.value !== '__new__' ? parseInt(addrSel.value) : null;
        var addrText = '';
        if (addrId) {
            var match = _addresses.filter(function (a) { return a.id === addrId; })[0];
            if (match) addrText = match.address_text;
        }
        return {
            customer_account: document.getElementById('customerAccount').value,
            customer_name: (document.getElementById('customerChipText').textContent || '').split(' (')[0],
            ship_date: document.getElementById('shipDate').value,
            delivery_address_id: addrId,
            delivery_address_text: addrText,
            ship_method: document.getElementById('shipMethod').value,
            po_number: document.getElementById('poNumber').value,
        };
    }

    function addLine() {
        if (!_selectedItem) { _showToast('Select an item first', 'error'); return; }
        var qty = parseInt(document.getElementById('lineQty').value) || 0;
        if (qty <= 0) { _showToast('Quantity must be greater than 0', 'error'); return; }

        var customPrice = parseFloat(document.getElementById('customPrice').value);
        var unitPrice = _selectedItem.customer_price || 0;
        var effectivePrice = (!isNaN(customPrice) && customPrice > 0) ? customPrice : unitPrice;

        var lineData = {
            item_number: _selectedItem.item_number,
            item_name: _selectedItem.item_name,
            upc: _selectedItem.upc || '',
            qty: qty,
            case_pack: _selectedItem.case_pack || 1,
            unit_price: unitPrice,
            custom_price: (!isNaN(customPrice) && customPrice > 0) ? customPrice : null,
            update_customer_price: document.getElementById('updateCustomerPrice').checked,
            book_price: _selectedItem.book_price || 0,
        };

        _ensureOrder().then(function (orderId) {
            return _api('POST', '/api/orders/' + orderId + '/lines', lineData);
        }).then(function (d) {
            if (d.success) {
                lineData.id = d.id;
                lineData.extended_price = qty * effectivePrice;
                _lines.push(lineData);
                _renderLines();
                clearItem();
                _showToast('Line added', 'success');
            }
        });
    }

    function removeLine(lineId) {
        if (!_orderId) return;
        _api('DELETE', '/api/orders/' + _orderId + '/lines/' + lineId).then(function (d) {
            if (d.success) {
                _lines = _lines.filter(function (l) { return l.id !== lineId; });
                _renderLines();
                _showToast('Line removed', 'success');
            }
        });
    }

    function _renderLines() {
        var container = document.getElementById('linesList');
        var header = document.getElementById('linesListHeader');
        var badge = document.getElementById('linesBadge');
        badge.textContent = _lines.length;

        if (!_lines.length) {
            container.innerHTML = '<div class="empty-state" style="padding:24px;"><p style="color:var(--text-muted);">No lines added yet.</p></div>';
            header.style.display = 'none';
            return;
        }

        header.style.display = 'flex';
        var total = 0;
        var html = '';
        _lines.forEach(function (l) {
            var price = l.custom_price || l.unit_price || 0;
            var ext = l.qty * price;
            total += ext;
            html += '<div class="oe-line-card" data-id="' + l.id + '">'
                  + '<div class="oe-line-card-body">'
                  + '<div class="oe-line-card-top">'
                  + '<span class="oe-line-item-name">' + (l.item_name || l.item_number) + '</span>'
                  + '<span class="oe-line-ext">' + _formatCurrency(ext) + '</span>'
                  + '</div>'
                  + '<div class="oe-line-card-meta">'
                  + '<span>' + l.item_number + '</span>'
                  + '<span>Qty: ' + l.qty + '</span>'
                  + '<span>@ ' + _formatCurrency(price) + '</span>'
                  + (l.update_customer_price ? '<span class="oe-line-flag">Price update</span>' : '')
                  + '</div>'
                  + '</div>'
                  + '<button class="oe-line-remove" onclick="OE.removeLine(' + l.id + ')" title="Remove line">'
                  + '<i data-feather="x" style="width:16px;height:16px;"></i>'
                  + '</button>'
                  + '</div>';
        });
        container.innerHTML = html;
        document.getElementById('linesTotalDisplay').textContent = 'Total: ' + _formatCurrency(total);
        if (typeof feather !== 'undefined') feather.replace();
    }

    // -- Matrix entry ---------------------------------------------------------

    var _matrixData = null;

    function setEntryMode(mode) {
        _entryMode = mode;
        document.querySelectorAll('.oe-mode-btn').forEach(function (b) {
            b.classList.toggle('active', b.getAttribute('data-mode') === mode);
        });
        document.getElementById('singleEntry').style.display = mode === 'single' ? 'block' : 'none';
        document.getElementById('matrixEntry').style.display = mode === 'matrix' ? 'block' : 'none';
    }

    function _getItemGroups(query) {
        var groups = {};
        var source = query ? _filterItems(query) : _allItems;
        source.forEach(function (it) {
            var g = it.group || it.item_name;
            if (!groups[g]) groups[g] = { name: g, sample: it, count: 0 };
            groups[g].count++;
        });
        return Object.keys(groups).map(function (k) { return groups[k]; });
    }

    function searchMatrixItems(query) {
        var groups = _getItemGroups(query);
        var dd = document.getElementById('matrixItemDropdown');
        if (!groups.length) { dd.style.display = 'none'; return; }

        dd.innerHTML = groups.map(function (g) {
            return '<div class="oe-dropdown-item" data-group="' + g.name + '" data-item-number="' + g.sample.item_number + '">'
                 + '<span class="oe-dd-primary">' + g.name + '</span>'
                 + '<span class="oe-dd-secondary">' + g.count + ' items</span>'
                 + '</div>';
        }).join('');
        dd.style.display = 'block';

        dd.querySelectorAll('.oe-dropdown-item').forEach(function (el) {
            el.addEventListener('click', function () {
                var groupName = this.getAttribute('data-group');
                var itemNum = this.getAttribute('data-item-number');
                _loadMatrix(groupName, itemNum);
                dd.style.display = 'none';
                document.getElementById('matrixItemSearch').value = groupName;
            });
        });
    }

    function showMatrixDropdown() {
        var query = document.getElementById('matrixItemSearch').value.trim();
        searchMatrixItems(query);
    }

    function _loadMatrix(groupName, itemNumber) {
        var lookup = encodeURIComponent(groupName || itemNumber);
        _api('GET', '/api/items/' + lookup + '/variants').then(function (data) {
            _matrixData = data;
            _renderMatrix(data);
        });
    }

    function _renderMatrix(data) {
        var grid = document.getElementById('matrixGrid');
        if (!data.colors.length || !data.sizes.length) {
            grid.style.display = 'none';
            _showToast('No variant matrix available for this product', 'info');
            return;
        }
        grid.style.display = 'block';

        var thead = document.getElementById('matrixHead');
        var headerRow = '<tr><th class="oe-matrix-corner"></th>';
        data.colors.forEach(function (c) {
            headerRow += '<th>' + c + '</th>';
        });
        headerRow += '</tr>';
        thead.innerHTML = headerRow;

        var tbody = document.getElementById('matrixBody');
        var bodyHtml = '';
        data.sizes.forEach(function (s) {
            bodyHtml += '<tr><td class="oe-matrix-row-label">' + s + '</td>';
            data.colors.forEach(function (c) {
                var cell = (data.grid[c] || {})[s];
                if (cell && cell.available) {
                    var cp = cell.case_pack || 1;
                    bodyHtml += '<td><input type="number" class="oe-matrix-input" min="0" step="' + cp + '" value="0"'
                              + ' data-color="' + c + '" data-size="' + s + '" data-sku="' + (cell.sku || '') + '"'
                              + ' data-case-pack="' + cp + '"'
                              + ' onchange="OE.snapMatrixQty(this)"></td>';
                } else {
                    bodyHtml += '<td class="oe-matrix-unavail"></td>';
                }
            });
            bodyHtml += '</tr>';
        });
        tbody.innerHTML = bodyHtml;
    }

    function snapMatrixQty(input) {
        var cp = parseInt(input.getAttribute('data-case-pack')) || 1;
        var val = parseInt(input.value) || 0;
        if (cp > 1 && val > 0 && val % cp !== 0) {
            val = Math.round(val / cp) * cp;
            if (val < cp) val = cp;
            input.value = val;
        }
    }

    function _lookupItemBySku(sku) {
        for (var i = 0; i < _allItems.length; i++) {
            if (_allItems[i].item_number === sku) return _allItems[i];
        }
        return null;
    }

    function addMatrixToOrder() {
        if (!_matrixData) return;
        var inputs = document.querySelectorAll('.oe-matrix-input');
        var linesToAdd = [];
        inputs.forEach(function (inp) {
            var qty = parseInt(inp.value) || 0;
            if (qty <= 0) return;
            var sku = inp.getAttribute('data-sku') || _matrixData.item_number;
            var catalogItem = _lookupItemBySku(sku);
            var unitPrice = catalogItem ? catalogItem.customer_price : 0;
            var bookPrice = catalogItem ? catalogItem.book_price : 0;
            var itemName = catalogItem ? catalogItem.item_name
                : (_matrixData.item_number + ' / ' + inp.getAttribute('data-color') + ' / ' + inp.getAttribute('data-size'));
            linesToAdd.push({
                item_number: sku,
                item_name: itemName,
                qty: qty,
                case_pack: parseInt(inp.getAttribute('data-case-pack')) || 1,
                unit_price: unitPrice,
                book_price: bookPrice,
                is_matrix_entry: true,
                variant_color: inp.getAttribute('data-color'),
                variant_size: inp.getAttribute('data-size'),
            });
        });

        if (!linesToAdd.length) { _showToast('Enter quantities in the matrix first', 'error'); return; }

        _ensureOrder().then(function (orderId) {
            var chain = Promise.resolve();
            linesToAdd.forEach(function (ld) {
                chain = chain.then(function () {
                    return _api('POST', '/api/orders/' + orderId + '/lines', ld).then(function (d) {
                        if (d.success) {
                            ld.id = d.id;
                            ld.extended_price = ld.qty * (ld.custom_price || ld.unit_price || 0);
                            _lines.push(ld);
                        }
                    });
                });
            });
            return chain;
        }).then(function () {
            _renderLines();
            inputs.forEach(function (inp) { inp.value = 0; });
            _showToast(linesToAdd.length + ' lines added from matrix', 'success');
        });
    }

    // -- Barcode scanner ------------------------------------------------------

    function openScanner() {
        document.getElementById('scannerModal').style.display = 'flex';
        var video = document.getElementById('scannerVideo');
        if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
            navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } })
                .then(function (stream) {
                    _scannerStream = stream;
                    video.srcObject = stream;
                })
                .catch(function () {
                    video.style.display = 'none';
                });
        } else {
            video.style.display = 'none';
        }
    }

    function closeScanner() {
        document.getElementById('scannerModal').style.display = 'none';
        if (_scannerStream) {
            _scannerStream.getTracks().forEach(function (t) { t.stop(); });
            _scannerStream = null;
        }
        document.getElementById('scannerVideo').srcObject = null;
    }

    function lookupUpc() {
        var upc = document.getElementById('manualUpc').value.trim();
        if (!upc) { _showToast('Enter a UPC code', 'error'); return; }
        _api('GET', '/api/items/scan/' + encodeURIComponent(upc)).then(function (data) {
            if (data.error) {
                _showToast(data.error, 'error');
            } else {
                _selectItem(data);
                closeScanner();
                setEntryMode('single');
            }
        });
    }

    // -- Save / submit / delete -----------------------------------------------

    function saveDraft() {
        var header = _gatherHeader();
        if (_orderId) {
            _api('PUT', '/api/orders/' + _orderId, header).then(function (d) {
                _showToast(d.success ? 'Draft saved' : (d.error || 'Save failed'), d.success ? 'success' : 'error');
            });
        } else {
            _api('POST', '/api/orders', header).then(function (d) {
                if (d.id) {
                    _orderId = d.id;
                    history.replaceState(null, '', '/orders/' + _orderId);
                    _showToast('Draft created', 'success');
                }
            });
        }
    }

    function submitOrder() {
        if (!_orderId) {
            _showToast('Save the order first', 'error');
            return;
        }
        var header = _gatherHeader();
        _api('PUT', '/api/orders/' + _orderId, header).then(function () {
            return _api('POST', '/api/orders/' + _orderId + '/submit');
        }).then(function (d) {
            if (d.success) {
                _showToast('Order submitted!', 'success');
                setTimeout(function () { window.location.href = '/orders'; }, 1000);
            } else if (d.missing) {
                _showToast('Missing: ' + d.missing.join(', '), 'error');
            } else {
                _showToast(d.error || 'Submit failed', 'error');
            }
        });
    }

    function deleteOrder() {
        if (!_orderId) return;
        if (!confirm('Delete this draft order?')) return;
        _api('DELETE', '/api/orders/' + _orderId).then(function (d) {
            if (d.success) {
                _showToast('Order deleted', 'success');
                setTimeout(function () { window.location.href = '/orders'; }, 500);
            }
        });
    }

    // -- Refresh product/pricing cache ----------------------------------------

    function refreshCache() {
        var btn = document.getElementById('refreshCacheBtn');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<i data-feather="loader" style="width:15px;height:15px;"></i> Refreshing...';
            if (typeof feather !== 'undefined') feather.replace();
        }
        _showToast('Refreshing product & pricing data from D365...', 'info');

        _api('POST', '/api/orders/refresh-cache').then(function (d) {
            if (d.success) {
                _showToast('Refresh started. Data will update in 1-2 minutes.', 'success');
                setTimeout(function () {
                    _loadItems();
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = '<i data-feather="refresh-cw" style="width:15px;height:15px;"></i> Refresh Data';
                        if (typeof feather !== 'undefined') feather.replace();
                    }
                }, 60000);
            }
        }).catch(function () {
            _showToast('Refresh failed', 'error');
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '<i data-feather="refresh-cw" style="width:15px;height:15px;"></i> Refresh Data';
                if (typeof feather !== 'undefined') feather.replace();
            }
        });
    }

    // -- Google Places Autocomplete -------------------------------------------

    var _placesAutocomplete = null;

    function _onPlacesReady() {
        var acInput = document.getElementById('newAddrAutocomplete');
        if (!acInput || !window.google || !window.google.maps || !window.google.maps.places) return;

        _placesAutocomplete = new google.maps.places.Autocomplete(acInput, {
            types: ['address'],
            componentRestrictions: { country: 'us' },
            fields: ['address_components', 'formatted_address'],
        });

        _placesAutocomplete.addListener('place_changed', function () {
            var place = _placesAutocomplete.getPlace();
            if (!place || !place.address_components) return;
            _applyPlaceComponents(place.address_components);
        });
    }

    function _applyPlaceComponents(components) {
        var streetNum = '', route = '', city = '', state = '', zip = '', country = '';
        components.forEach(function (c) {
            var types = c.types;
            if (types.indexOf('street_number') !== -1) streetNum = c.long_name;
            else if (types.indexOf('route') !== -1) route = c.long_name;
            else if (types.indexOf('locality') !== -1) city = c.long_name;
            else if (types.indexOf('sublocality_level_1') !== -1 && !city) city = c.long_name;
            else if (types.indexOf('administrative_area_level_1') !== -1) state = c.short_name;
            else if (types.indexOf('postal_code') !== -1) zip = c.long_name;
            else if (types.indexOf('country') !== -1) country = c.short_name;
        });

        document.getElementById('newAddrStreet').value = (streetNum + ' ' + route).trim();
        document.getElementById('newAddrCity').value = city;
        document.getElementById('newAddrState').value = state;
        document.getElementById('newAddrZip').value = zip;
        document.getElementById('newAddrCountry').value = country || 'US';
        _showParsedAddress();

        if (!document.getElementById('newAddressLabel').value) autoGenAddrLabel();
        if (!document.getElementById('newAddrId').value) autoGenAddrId();
    }

    function _initFallbackAutocomplete() {
        var acInput = document.getElementById('newAddrAutocomplete');
        if (!acInput) return;
        acInput.placeholder = 'Enter address (Street, City, State Zip)';
        acInput.addEventListener('keydown', function (e) {
            if (e.key !== 'Enter') return;
            e.preventDefault();
            var raw = acInput.value.trim();
            if (!raw) return;
            var parts = raw.split(',').map(function (s) { return s.trim(); });
            var street = parts[0] || '';
            var city = parts[1] || '';
            var stateZip = (parts[2] || '').trim().split(/\s+/);
            var state = stateZip[0] || '';
            var zip = stateZip[1] || '';
            var country = parts[3] || 'US';

            document.getElementById('newAddrStreet').value = street;
            document.getElementById('newAddrCity').value = city;
            document.getElementById('newAddrState').value = state;
            document.getElementById('newAddrZip').value = zip;
            document.getElementById('newAddrCountry').value = country;
            _showParsedAddress();
            if (!document.getElementById('newAddressLabel').value) autoGenAddrLabel();
            if (!document.getElementById('newAddrId').value) autoGenAddrId();
        });
    }

    // -- Init -----------------------------------------------------------------

    function init() {
        _loadCustomers();
        _loadItems();
        _loadShipMethods();

        if (typeof ORDER_DATA !== 'undefined' && ORDER_DATA.customer_account) {
            _selectCustomer(ORDER_DATA.customer_account, ORDER_DATA.customer_name || ORDER_DATA.customer_account);
            if (ORDER_DATA.delivery_address_id) {
                setTimeout(function () {
                    var addr = _addresses.filter(function (a) { return a.id === ORDER_DATA.delivery_address_id; })[0];
                    if (addr) {
                        _selectAddress(addr);
                    } else {
                        document.getElementById('addressSelect').value = ORDER_DATA.delivery_address_id;
                        if (ORDER_DATA.delivery_address_text) {
                            document.getElementById('addressChip').style.display = 'flex';
                            document.getElementById('addressChipText').textContent = ORDER_DATA.delivery_address_text;
                        }
                    }
                }, 800);
            }
        }

        _renderLines();

        document.addEventListener('click', function (e) {
            if (!e.target.closest('.oe-search-wrap')) {
                _closeAllDropdowns();
            }
        });
    }

    document.addEventListener('DOMContentLoaded', init);

    // -- Public API -----------------------------------------------------------

    return {
        switchTab: switchTab,
        searchCustomers: searchCustomers,
        showCustomerDropdown: showCustomerDropdown,
        clearCustomer: clearCustomer,
        searchAddresses: searchAddresses,
        showAddressDropdown: showAddressDropdown,
        clearAddress: clearAddress,
        onAddressChange: onAddressChange,
        saveNewAddress: saveNewAddress,
        cancelNewAddress: cancelNewAddress,
        clearParsedAddress: clearParsedAddress,
        autoGenAddrId: autoGenAddrId,
        autoGenAddrLabel: autoGenAddrLabel,
        generatePO: generatePO,
        searchItems: searchItems,
        showItemDropdown: showItemDropdown,
        clearItem: clearItem,
        adjustQty: adjustQty,
        onQtyChange: onQtyChange,
        recalcExtended: recalcExtended,
        addLine: addLine,
        removeLine: removeLine,
        setEntryMode: setEntryMode,
        searchMatrixItems: searchMatrixItems,
        showMatrixDropdown: showMatrixDropdown,
        snapMatrixQty: snapMatrixQty,
        addMatrixToOrder: addMatrixToOrder,
        openScanner: openScanner,
        closeScanner: closeScanner,
        lookupUpc: lookupUpc,
        saveDraft: saveDraft,
        submitOrder: submitOrder,
        deleteOrder: deleteOrder,
        refreshCache: refreshCache,
        _onPlacesReady: _onPlacesReady,
        _initFallbackAutocomplete: _initFallbackAutocomplete,
    };
})();
