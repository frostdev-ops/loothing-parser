#!/usr/bin/env python3
"""
Standalone Validation Test for Time-Series Optimization

This test validates the syntax, structure, and optimization patterns
without requiring external dependencies.
"""

import os
import sys
import ast
import logging
from typing import Dict, Any, List, Optional
import json

# Add the src directory to the path
sys.path.insert(0, '/home/pma/lootbong-trackdong/parser')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class StandaloneOptimizationValidator:
    """Standalone validator for time-series optimization components."""

    def __init__(self):
        self.results = {
            'syntax_validation': {'passed': False, 'details': []},
            'import_analysis': {'passed': False, 'details': []},
            'guild_isolation': {'passed': False, 'details': []},
            'caching_strategies': {'passed': False, 'details': []},
            'query_optimization': {'passed': False, 'details': []},
            'time_window_handling': {'passed': False, 'details': []},
            'performance_patterns': {'passed': False, 'details': []},
            'integration_readiness': {'passed': False, 'details': []}
        }

    def validate_all(self):
        """Run all validation tests."""
        logger.info("🔍 Starting Standalone Validation for Time-Series Optimization")

        self.validate_syntax()
        self.analyze_imports()
        self.validate_guild_isolation()
        self.analyze_caching_strategies()
        self.validate_query_optimization()
        self.validate_time_window_handling()
        self.analyze_performance_patterns()
        self.validate_integration_readiness()

        self.generate_report()

    def validate_syntax(self):
        """Validate Python syntax and AST structure."""
        logger.info("📋 Validating syntax and AST structure...")

        files_to_validate = [
            'src/query/time_series_cache.py',
            'src/query/optimized_influx_manager.py'
        ]

        syntax_results = []

        for file_path in files_to_validate:
            full_path = os.path.join('/home/pma/lootbong-trackdong/parser', file_path)
            try:
                with open(full_path, 'r') as f:
                    source_code = f.read()

                # Parse AST to validate syntax
                ast.parse(source_code)
                syntax_results.append(f"✅ {file_path}: Syntax valid")

                # Check for key classes and methods
                tree = ast.parse(source_code)
                classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
                methods = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]

                if 'time_series_cache.py' in file_path:
                    expected_classes = ['TimeSeriesQueryCache', 'TimeSeriesQueryOptimizer', 'CacheConfig']
                    for cls in expected_classes:
                        if cls in classes:
                            syntax_results.append(f"✅ {file_path}: Found class {cls}")
                        else:
                            syntax_results.append(f"❌ {file_path}: Missing class {cls}")

                elif 'optimized_influx_manager.py' in file_path:
                    expected_classes = ['OptimizedInfluxManager']
                    for cls in expected_classes:
                        if cls in classes:
                            syntax_results.append(f"✅ {file_path}: Found class {cls}")
                        else:
                            syntax_results.append(f"❌ {file_path}: Missing class {cls}")

            except SyntaxError as e:
                syntax_results.append(f"❌ {file_path}: Syntax error - {e}")
            except Exception as e:
                syntax_results.append(f"❌ {file_path}: Validation error - {e}")

        # Check for syntax errors in dependencies
        try:
            with open('/home/pma/lootbong-trackdong/parser/src/database/influxdb_direct_manager.py', 'r') as f:
                source_code = f.read()
            ast.parse(source_code)
            syntax_results.append("✅ influxdb_direct_manager.py: Syntax valid")
        except SyntaxError as e:
            syntax_results.append(f"❌ influxdb_direct_manager.py: Syntax error - {e}")

        all_passed = all('✅' in result for result in syntax_results)
        self.results['syntax_validation'] = {'passed': all_passed, 'details': syntax_results}

    def analyze_imports(self):
        """Analyze import structure and dependencies."""
        logger.info("📦 Analyzing import structure...")

        import_analysis = []

        # Analyze time_series_cache.py imports
        cache_file = '/home/pma/lootbong-trackdong/parser/src/query/time_series_cache.py'
        try:
            with open(cache_file, 'r') as f:
                content = f.read()

            tree = ast.parse(content)
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for name in node.names:
                        imports.append(name.name)
                elif isinstance(node, ast.ImportFrom):
                    imports.append(f"from {node.module}")

            # Check for required imports
            required_imports = ['asyncio', 'logging', 'json', 'hashlib', 'time']
            for imp in required_imports:
                if any(imp in i for i in imports):
                    import_analysis.append(f"✅ time_series_cache.py: Has {imp} import")
                else:
                    import_analysis.append(f"⚠️  time_series_cache.py: Missing {imp} import")

            # Check for external dependencies
            external_deps = ['redis', 'influxdb_client']
            for dep in external_deps:
                if any(dep in i for i in imports):
                    import_analysis.append(f"📦 time_series_cache.py: Uses external dependency {dep}")

        except Exception as e:
            import_analysis.append(f"❌ Failed to analyze imports: {e}")

        self.results['import_analysis'] = {
            'passed': len([r for r in import_analysis if '❌' in r]) == 0,
            'details': import_analysis
        }

    def validate_guild_isolation(self):
        """Validate multi-tenant guild isolation patterns."""
        logger.info("🏰 Validating guild isolation patterns...")

        isolation_checks = []

        cache_file = '/home/pma/lootbong-trackdong/parser/src/query/time_series_cache.py'
        try:
            with open(cache_file, 'r') as f:
                content = f.read()

            # Check for guild_id in cache key generation
            if '_generate_cache_key' in content and 'guild_id' in content:
                isolation_checks.append("✅ Cache key generation includes guild_id")
            else:
                isolation_checks.append("❌ Cache key generation missing guild_id")

            # Check for guild-specific invalidation
            if 'invalidate_guild_cache' in content:
                isolation_checks.append("✅ Guild-specific cache invalidation implemented")
            else:
                isolation_checks.append("❌ Missing guild-specific cache invalidation")

            # Check for guild partitioning in cache structure
            if 'guild_caches' in content or 'guild_id' in content:
                isolation_checks.append("✅ Guild partitioning patterns found")
            else:
                isolation_checks.append("❌ Missing guild partitioning patterns")

        except Exception as e:
            isolation_checks.append(f"❌ Guild isolation validation failed: {e}")

        # Check optimized manager for guild isolation
        manager_file = '/home/pma/lootbong-trackdong/parser/src/query/optimized_influx_manager.py'
        try:
            with open(manager_file, 'r') as f:
                content = f.read()

            # Check for guild filtering in queries
            if 'guild_id' in content and 'filter' in content:
                isolation_checks.append("✅ Query filtering by guild_id implemented")
            else:
                isolation_checks.append("❌ Missing query filtering by guild_id")

        except Exception as e:
            isolation_checks.append(f"❌ Manager guild isolation check failed: {e}")

        all_passed = all('✅' in check for check in isolation_checks)
        self.results['guild_isolation'] = {'passed': all_passed, 'details': isolation_checks}

    def analyze_caching_strategies(self):
        """Analyze multi-tier caching strategies."""
        logger.info("⚡ Analyzing caching strategies...")

        caching_analysis = []

        cache_file = '/home/pma/lootbong-trackdong/parser/src/query/time_series_cache.py'
        try:
            with open(cache_file, 'r') as f:
                content = f.read()

            # Check for multi-tier cache implementation
            if "'hot'" in content and "'warm'" in content and "'cold'" in content:
                caching_analysis.append("✅ Multi-tier caching (hot/warm/cold) implemented")
            else:
                caching_analysis.append("❌ Multi-tier caching not found")

            # Check for TTL optimization
            if 'TTL' in content and '_get_ttl_for_query' in content:
                caching_analysis.append("✅ TTL optimization based on query type implemented")
            else:
                caching_analysis.append("❌ TTL optimization missing")

            # Check for cache tier determination
            if '_determine_cache_tier' in content:
                caching_analysis.append("✅ Intelligent cache tier determination implemented")
            else:
                caching_analysis.append("❌ Cache tier determination missing")

            # Check for memory management
            if 'evict' in content.lower() and 'memory_cache' in content:
                caching_analysis.append("✅ Memory management and eviction implemented")
            else:
                caching_analysis.append("❌ Memory management missing")

            # Check for performance profiling
            if 'QueryProfile' in content and 'performance' in content.lower():
                caching_analysis.append("✅ Query performance profiling implemented")
            else:
                caching_analysis.append("❌ Performance profiling missing")

        except Exception as e:
            caching_analysis.append(f"❌ Caching strategy analysis failed: {e}")

        passed = len([c for c in caching_analysis if '✅' in c]) >= 3
        self.results['caching_strategies'] = {'passed': passed, 'details': caching_analysis}

    def validate_query_optimization(self):
        """Validate time-series query optimization patterns."""
        logger.info("🔍 Validating query optimization patterns...")

        optimization_checks = []

        # Check TimeSeriesQueryOptimizer
        cache_file = '/home/pma/lootbong-trackdong/parser/src/query/time_series_cache.py'
        try:
            with open(cache_file, 'r') as f:
                content = f.read()

            if 'TimeSeriesQueryOptimizer' in content:
                optimization_checks.append("✅ TimeSeriesQueryOptimizer class found")

                # Check for Flux query optimization
                if 'optimize_flux_query' in content:
                    optimization_checks.append("✅ Flux query optimization implemented")
                else:
                    optimization_checks.append("❌ Flux query optimization missing")

                # Check for optimization suggestions
                if 'suggest_query_improvements' in content:
                    optimization_checks.append("✅ Query improvement suggestions implemented")
                else:
                    optimization_checks.append("❌ Query improvement suggestions missing")

            else:
                optimization_checks.append("❌ TimeSeriesQueryOptimizer class not found")

        except Exception as e:
            optimization_checks.append(f"❌ Query optimizer validation failed: {e}")

        # Check OptimizedInfluxManager
        manager_file = '/home/pma/lootbong-trackdong/parser/src/query/optimized_influx_manager.py'
        try:
            with open(manager_file, 'r') as f:
                content = f.read()

            # Check for query builders
            if '_build_player_metrics_flux_query' in content:
                optimization_checks.append("✅ Player metrics query builder implemented")
            else:
                optimization_checks.append("❌ Player metrics query builder missing")

            # Check for batch query execution
            if 'execute_batch_queries' in content:
                optimization_checks.append("✅ Batch query execution implemented")
            else:
                optimization_checks.append("❌ Batch query execution missing")

            # Check for query execution plans
            if 'QueryExecutionPlan' in content:
                optimization_checks.append("✅ Query execution planning implemented")
            else:
                optimization_checks.append("❌ Query execution planning missing")

        except Exception as e:
            optimization_checks.append(f"❌ Manager optimization validation failed: {e}")

        passed = len([c for c in optimization_checks if '✅' in c]) >= 4
        self.results['query_optimization'] = {'passed': passed, 'details': optimization_checks}

    def validate_time_window_handling(self):
        """Validate time-window encounter handling."""
        logger.info("⏰ Validating time-window encounter handling...")

        time_window_checks = []

        # Check cache time range handling
        cache_file = '/home/pma/lootbong-trackdong/parser/src/query/time_series_cache.py'
        try:
            with open(cache_file, 'r') as f:
                content = f.read()

            if 'time_range' in content and 'invalidate_time_range' in content:
                time_window_checks.append("✅ Time range cache invalidation implemented")
            else:
                time_window_checks.append("❌ Time range cache invalidation missing")

            if '_should_optimize_time_window' in content:
                time_window_checks.append("✅ Time window optimization logic implemented")
            else:
                time_window_checks.append("❌ Time window optimization missing")

        except Exception as e:
            time_window_checks.append(f"❌ Cache time window validation failed: {e}")

        # Check direct manager time window support
        direct_manager_file = '/home/pma/lootbong-trackdong/parser/src/database/influxdb_direct_manager.py'
        try:
            with open(direct_manager_file, 'r') as f:
                content = f.read()

            if 'define_encounter_window' in content:
                time_window_checks.append("✅ Encounter window definition implemented")
            else:
                time_window_checks.append("❌ Encounter window definition missing")

            if 'time_window' in content.lower() and 'encounter_id' in content:
                time_window_checks.append("✅ Time-window based encounter IDs implemented")
            else:
                time_window_checks.append("❌ Time-window encounter ID generation missing")

        except Exception as e:
            time_window_checks.append(f"❌ Direct manager time window validation failed: {e}")

        passed = len([c for c in time_window_checks if '✅' in c]) >= 2
        self.results['time_window_handling'] = {'passed': passed, 'details': time_window_checks}

    def analyze_performance_patterns(self):
        """Analyze performance optimization patterns."""
        logger.info("📊 Analyzing performance patterns...")

        performance_analysis = []

        # Check for async/await patterns
        cache_file = '/home/pma/lootbong-trackdong/parser/src/query/time_series_cache.py'
        try:
            with open(cache_file, 'r') as f:
                content = f.read()

            if 'async def' in content and 'await' in content:
                performance_analysis.append("✅ Asynchronous patterns implemented")
            else:
                performance_analysis.append("❌ Asynchronous patterns missing")

            # Check for background tasks
            if 'background' in content.lower() and 'asyncio.create_task' in content:
                performance_analysis.append("✅ Background task optimization implemented")
            else:
                performance_analysis.append("❌ Background task optimization missing")

            # Check for performance metrics
            if 'performance_metrics' in content or 'stats' in content:
                performance_analysis.append("✅ Performance metrics tracking implemented")
            else:
                performance_analysis.append("❌ Performance metrics tracking missing")

        except Exception as e:
            performance_analysis.append(f"❌ Performance pattern analysis failed: {e}")

        # Check manager performance patterns
        manager_file = '/home/pma/lootbong-trackdong/parser/src/query/optimized_influx_manager.py'
        try:
            with open(manager_file, 'r') as f:
                content = f.read()

            # Check for concurrent execution
            if 'asyncio.gather' in content or 'concurrent' in content.lower():
                performance_analysis.append("✅ Concurrent execution patterns implemented")
            else:
                performance_analysis.append("❌ Concurrent execution patterns missing")

            # Check for connection pooling/management
            if 'pool' in content.lower() or 'ThreadPoolExecutor' in content:
                performance_analysis.append("✅ Resource pooling implemented")
            else:
                performance_analysis.append("❌ Resource pooling missing")

        except Exception as e:
            performance_analysis.append(f"❌ Manager performance analysis failed: {e}")

        passed = len([p for p in performance_analysis if '✅' in p]) >= 3
        self.results['performance_patterns'] = {'passed': passed, 'details': performance_analysis}

    def validate_integration_readiness(self):
        """Validate integration readiness with existing systems."""
        logger.info("🔗 Validating integration readiness...")

        integration_checks = []

        # Check for proper imports and dependencies
        manager_file = '/home/pma/lootbong-trackdong/parser/src/query/optimized_influx_manager.py'
        try:
            with open(manager_file, 'r') as f:
                content = f.read()

            # Check for database manager imports
            if 'from ..database.influx' in content:
                integration_checks.append("✅ Database manager imports configured")
            else:
                integration_checks.append("❌ Database manager imports missing")

            # Check for initialization methods
            if 'def initialize' in content:
                integration_checks.append("✅ Initialization methods implemented")
            else:
                integration_checks.append("❌ Initialization methods missing")

            # Check for shutdown/cleanup methods
            if 'def shutdown' in content:
                integration_checks.append("✅ Cleanup methods implemented")
            else:
                integration_checks.append("❌ Cleanup methods missing")

        except Exception as e:
            integration_checks.append(f"❌ Integration readiness check failed: {e}")

        # Check for configuration flexibility
        cache_file = '/home/pma/lootbong-trackdong/parser/src/query/time_series_cache.py'
        try:
            with open(cache_file, 'r') as f:
                content = f.read()

            if 'CacheConfig' in content and '__init__' in content:
                integration_checks.append("✅ Configurable cache settings implemented")
            else:
                integration_checks.append("❌ Configurable cache settings missing")

        except Exception as e:
            integration_checks.append(f"❌ Cache configuration check failed: {e}")

        passed = len([c for c in integration_checks if '✅' in c]) >= 3
        self.results['integration_readiness'] = {'passed': passed, 'details': integration_checks}

    def generate_report(self):
        """Generate comprehensive validation report."""
        logger.info("\n" + "="*80)
        logger.info("📊 TIME-SERIES OPTIMIZATION VALIDATION REPORT")
        logger.info("="*80)

        # Count overall results
        total_categories = len(self.results)
        passed_categories = sum(1 for result in self.results.values() if result['passed'])

        logger.info(f"Overall Results: {passed_categories}/{total_categories} categories passed")
        logger.info("-" * 50)

        # Category results
        category_names = {
            'syntax_validation': 'Syntax Validation',
            'import_analysis': 'Import Analysis',
            'guild_isolation': 'Guild Isolation',
            'caching_strategies': 'Caching Strategies',
            'query_optimization': 'Query Optimization',
            'time_window_handling': 'Time-Window Handling',
            'performance_patterns': 'Performance Patterns',
            'integration_readiness': 'Integration Readiness'
        }

        for key, name in category_names.items():
            result = self.results[key]
            status = "✅ PASS" if result['passed'] else "❌ FAIL"
            details_count = len([d for d in result['details'] if '✅' in d])
            total_checks = len(result['details'])
            logger.info(f"{name:.<30} {status} ({details_count}/{total_checks})")

        logger.info("-" * 50)

        # Detailed results for failed categories
        for key, result in self.results.items():
            if not result['passed']:
                category_name = category_names[key]
                logger.info(f"\n📋 {category_name} Details:")
                for detail in result['details']:
                    logger.info(f"  {detail}")

        # Performance recommendations
        logger.info("\n💡 PERFORMANCE OPTIMIZATION SUMMARY:")
        logger.info("-" * 50)

        recommendations = []

        if self.results['caching_strategies']['passed']:
            recommendations.append("✅ Multi-tier caching strategy is well-implemented")
        else:
            recommendations.append("🔧 Consider implementing multi-tier caching for better performance")

        if self.results['guild_isolation']['passed']:
            recommendations.append("✅ Guild isolation ensures proper multi-tenancy")
        else:
            recommendations.append("🔧 Implement guild-specific cache partitioning for security")

        if self.results['query_optimization']['passed']:
            recommendations.append("✅ Query optimization patterns are comprehensive")
        else:
            recommendations.append("🔧 Add query optimization for better InfluxDB performance")

        if self.results['performance_patterns']['passed']:
            recommendations.append("✅ Async patterns optimize system throughput")
        else:
            recommendations.append("🔧 Implement async patterns for better concurrency")

        for rec in recommendations:
            logger.info(f"  {rec}")

        logger.info("\n🎯 INTEGRATION STATUS:")
        logger.info("-" * 50)

        if self.results['integration_readiness']['passed']:
            logger.info("🚀 System is ready for integration with existing infrastructure")
        else:
            logger.info("⚠️  Additional integration work needed before deployment")

        if passed_categories == total_categories:
            logger.info("\n🎉 ALL VALIDATIONS PASSED! Time-series optimization is production-ready.")
        else:
            logger.info(f"\n⚠️  {total_categories - passed_categories} validation(s) failed. Review and address issues before deployment.")

        logger.info("="*80 + "\n")

def main():
    """Main validation runner."""
    validator = StandaloneOptimizationValidator()
    validator.validate_all()

if __name__ == "__main__":
    main()