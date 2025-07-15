document.addEventListener('DOMContentLoaded', () => {
    // Highlight active navigation link
    const navLinks = document.querySelectorAll('nav a');
    const currentPath = window.location.pathname.split('/').pop();
    navLinks.forEach(link => {
        if (link.getAttribute('href') === currentPath) {
            link.classList.add('active');
        }
    });

    const tradeForm = document.getElementById('trade-form');
    const tradeHistoryTable = document.getElementById('trade-history-table')?.getElementsByTagName('tbody')[0];
    const initialBalanceInput = document.getElementById('initial-balance');
    const clearDataButton = document.getElementById('clear-data-button');

    let trades = JSON.parse(localStorage.getItem('trades')) || [];
    let initialBalance = localStorage.getItem('initialBalance') || 0;

    if (initialBalanceInput) {
        initialBalanceInput.value = initialBalance;
        if (!initialBalance || parseFloat(initialBalance) <= 0) {
            tradeForm.style.display = 'none';
        }
    }

    const saveInitialBalance = (balance) => {
        if (parseFloat(balance) > 0) {
            localStorage.setItem('initialBalance', balance);
            initialBalance = balance;
            if (tradeForm) {
                tradeForm.style.display = 'block';
            }
        } else {
            alert('Please enter a positive initial balance.');
        }
    };

    const saveTrades = () => {
        localStorage.setItem('trades', JSON.stringify(trades));
    };

    const calculateProfitLoss = (trade) => {
        if (trade.status === 'exit' && trade.exitPrice) {
            const entryValue = trade.entry;
            const exitValue = trade.exitPrice;
            if (trade.action === 'buy') {
                return exitValue - entryValue;
            } else { // sell
                return entryValue - exitValue;
            }
        }
        return 0;
    };

    const renderTradeHistory = () => {
        if (!tradeHistoryTable) return;

        tradeHistoryTable.innerHTML = '';
        trades.forEach(trade => {
            const row = tradeHistoryTable.insertRow();
            const profitLoss = calculateProfitLoss(trade);
            row.innerHTML = `
                <td>${trade.date}</td>
                <td>${trade.symbol}</td>
                <td>${trade.action}</td>
                <td>${trade.entry}</td>
                <td>${trade.tp}</td>
                <td>${trade.sl}</td>
                <td>${trade.status}</td>
                <td>${trade.exitPrice || ''}</td>
                <td>${profitLoss.toFixed(2)}</td>
            `;
        });
    };

    if (tradeForm) {
        tradeForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const newTrade = {
                date: document.getElementById('date').value,
                symbol: document.getElementById('symbol').value,
                action: document.getElementById('action').value,
                entry: parseFloat(document.getElementById('entry').value),
                tp: parseFloat(document.getElementById('tp').value),
                sl: parseFloat(document.getElementById('sl').value),
                status: document.getElementById('status').value,
                exitPrice: document.getElementById('exit-price').value ? parseFloat(document.getElementById('exit-price').value) : null,
            };
            trades.push(newTrade);
            saveTrades();
            renderTradeHistory();
            tradeForm.reset();
        });
    }

    if (initialBalanceInput) {
        initialBalanceInput.addEventListener('change', () => {
            saveInitialBalance(initialBalanceInput.value);
        });
    }

    if (clearDataButton) {
        clearDataButton.addEventListener('click', () => {
            if (confirm('Are you sure you want to clear all trading data? This action cannot be undone.')) {
                localStorage.removeItem('trades');
                localStorage.removeItem('initialBalance');
                trades = [];
                initialBalance = 0;
                if (initialBalanceInput) {
                    initialBalanceInput.value = 0;
                }
                if (tradeHistoryTable) {
                    renderTradeHistory();
                }
                alert('All data has been cleared.');
                window.location.reload();
            }
        });
    }

    // Initial render
    renderTradeHistory();
    renderDashboard();

    function renderDashboard() {
        if (document.getElementById('equity-curve-chart')) {
            renderEquityCurve();
            renderDrawdown();
            renderProfitMAScatter();
            renderDailyPLBarChart();
        }
    }

    function calculateEquityCurve() {
        let equity = parseFloat(initialBalance);
        const equityData = [equity];
        trades.forEach(trade => {
            equity += calculateProfitLoss(trade);
            equityData.push(equity);
        });
        return equityData;
    }

    function renderEquityCurve() {
        const ctx = document.getElementById('equity-curve-chart').getContext('2d');
        const equityData = calculateEquityCurve();
        new Chart(ctx, {
            type: 'line',
            data: {
                labels: ['Start', ...trades.map((_, i) => `Trade ${i + 1}`)],
                datasets: [{
                    label: 'Equity Curve',
                    data: equityData,
                    borderColor: 'rgba(75, 192, 192, 1)',
                    backgroundColor: 'rgba(75, 192, 192, 0.2)',
                    fill: true,
                }]
            },
        });
    }

    function calculateDrawdown() {
        const equityCurve = calculateEquityCurve();
        let peak = equityCurve[0];
        const drawdown = [];
        for (const equity of equityCurve) {
            if (equity > peak) {
                peak = equity;
            }
            const dd = ((peak - equity) / peak) * 100;
            drawdown.push(dd);
        }
        return drawdown;
    }

    function renderDrawdown() {
        const ctx = document.getElementById('drawdown-chart').getContext('2d');
        const drawdownData = calculateDrawdown();
        new Chart(ctx, {
            type: 'line',
            data: {
                labels: ['Start', ...trades.map((_, i) => `Trade ${i + 1}`)],
                datasets: [{
                    label: 'Drawdown (%)',
                    data: drawdownData,
                    borderColor: 'rgba(255, 99, 132, 1)',
                    backgroundColor: 'rgba(255, 99, 132, 0.2)',
                    fill: true,
                }]
            },
            options: {
                scales: {
                    y: {
                        ticks: {
                            callback: function(value) {
                                return value + '%';
                            }
                        }
                    }
                }
            }
        });
    }

    function renderProfitMAScatter() {
        const ctx = document.getElementById('profit-ma-scatter-plot').getContext('2d');
        const profits = trades.map(calculateProfitLoss);
        const movingAverage = [];
        const period = 10;
        for (let i = 0; i < profits.length; i++) {
            if (i < period - 1) {
                movingAverage.push(null);
            } else {
                const sum = profits.slice(i - period + 1, i + 1).reduce((a, b) => a + b, 0);
                movingAverage.push(sum / period);
            }
        }

        const scatterData = profits.map((profit, i) => ({
            x: movingAverage[i],
            y: profit
        })).filter(d => d.x !== null);

        new Chart(ctx, {
            type: 'scatter',
            data: {
                datasets: [{
                    label: 'Profit vs. MA',
                    data: scatterData,
                    backgroundColor: 'rgba(54, 162, 235, 0.6)'
                }]
            },
            options: {
                scales: {
                    x: {
                        title: {
                            display: true,
                            text: 'Moving Average'
                        }
                    },
                    y: {
                        title: {
                            display: true,
                            text: 'Profit'
                        }
                    }
                }
            }
        });
    }

    function renderDailyPLBarChart() {
        const ctx = document.getElementById('daily-pl-bar-chart').getContext('2d');
        const dailyPL = {};
        trades.forEach(trade => {
            const profit = calculateProfitLoss(trade);
            if (dailyPL[trade.date]) {
                dailyPL[trade.date] += profit;
            } else {
                dailyPL[trade.date] = profit;
            }
        });

        const labels = Object.keys(dailyPL).sort();
        const data = labels.map(date => dailyPL[date]);
        const backgroundColors = data.map(pl => pl >= 0 ? 'rgba(75, 192, 192, 0.6)' : 'rgba(255, 99, 132, 0.6)');

        new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Daily P/L',
                    data: data,
                    backgroundColor: backgroundColors,
                }]
            },
            options: {
                scales: {
                    y: {
                        beginAtZero: true
                    }
                }
            }
        });
    }

    function renderStatistics() {
        if (document.getElementById('statistics-container')) {
            const statsContainer = document.getElementById('statistics-container');
            statsContainer.innerHTML = ''; // Clear previous stats

            const profits = trades.map(calculateProfitLoss);
            const totalTrades = trades.length;
            const winningTrades = profits.filter(p => p > 0).length;
            const losingTrades = profits.filter(p => p < 0).length;
            const winRate = totalTrades > 0 ? (winningTrades / totalTrades) * 100 : 0;
            const totalProfit = profits.reduce((a, b) => a + b, 0);
            const averageProfit = totalTrades > 0 ? totalProfit / totalTrades : 0;
            const maxWin = Math.max(...profits, 0);
            const maxLoss = Math.min(...profits, 0);
            const profitFactor = Math.abs(profits.filter(p => p > 0).reduce((a, b) => a + b, 0) / profits.filter(p => p < 0).reduce((a, b) => a + b, 0)) || 0;

            const stats = {
                'Total Trades': totalTrades,
                'Winning Trades': winningTrades,
                'Losing Trades': losingTrades,
                'Win Rate': `${winRate.toFixed(2)}%`,
                'Total Profit': totalProfit.toFixed(2),
                'Average Profit': averageProfit.toFixed(2),
                'Max Win': maxWin.toFixed(2),
                'Max Loss': maxLoss.toFixed(2),
                'Profit Factor': profitFactor.toFixed(2)
            };

            for (const [key, value] of Object.entries(stats)) {
                const statCard = document.createElement('div');
                statCard.className = 'stat-card';
                statCard.innerHTML = `<h3>${key}</h3><p>${value}</p>`;
                statsContainer.appendChild(statCard);
            }

            renderPerformancePlot();
        }
    }

    function renderPerformancePlot() {
        const ctx = document.getElementById('performance-plot').getContext('2d');
        const profits = trades.map(calculateProfitLoss);
        new Chart(ctx, {
            type: 'bar',
            data: {
                labels: trades.map((_, i) => `Trade ${i + 1}`),
                datasets: [{
                    label: 'Profit/Loss per Trade',
                    data: profits,
                    backgroundColor: profits.map(p => p >= 0 ? 'rgba(75, 192, 192, 0.6)' : 'rgba(255, 99, 132, 0.6)'),
                }]
            }
        });
    }

    // Call renderStatistics on page load
    renderStatistics();
});
